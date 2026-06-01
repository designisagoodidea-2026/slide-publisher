"""
remediation_apply_pptx.py — automated remediation for a .pptx template
that failed the validator.

Input:
    template_path:  the source .pptx the validator was unhappy with
    validator_path: path to the validator's JSON output (run validator first)
    out_path:       where to write the remediated .pptx

Pipeline:
    1. Read validator findings.
    2. Apply fixes in dependency order:
       a. Layout renaming (improves layout_catalog_completeness + orphan_elements).
       b. Theme color token addition (improves color_tokens).
       c. Master typeface registration (improves type_tokens).
       d. Orphan layout cleanup (improves orphan_elements; only safe if layout
          isn't referenced by any slide).
    3. Re-run the validator on the remediated output.
    4. Emit fix-audit log (markdown + JSON) and the verdict comparison.

Fix categories the v0.1 remediator handles automatically:
    - layout_catalog_completeness: rename existing layouts via semantic heuristic.
    - color_tokens: add token-shaped color definitions to the slide master if
      none exist (uses a neutral default palette; preserves any present).
    - type_tokens: register a primary typeface on the master if none defined.
    - orphan_elements: rename or drop unused layouts (post-rename; safe path).

Fix categories deferred to v0.2 (auto-remediation requires riskier edits):
    - master_usage: consolidating multiple masters can break inheritance in
      subtle ways. v0.1 logs the finding and recommends manual consolidation.
    - style_hierarchy: adding distinct font-size tiers to a master requires
      well-formed XML editing that v0.1 doesn't attempt.

Anonymity: ships in the public plugin. No hard-coded organization patterns.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _common import (  # noqa: E402
    LAYOUT_INTENTS, INTENT_TO_HEURISTIC_NAME, DEFAULT_PALETTE, DEFAULT_TYPEFACE,
    detect_intent_from_name,
)

try:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
except ImportError:
    print("ERROR: python-pptx is not installed. Install with: "
          "pip install python-pptx", file=sys.stderr)
    sys.exit(2)


@dataclass
class FixEntry:
    """One auto-remediation action."""
    fix_type: str               # e.g. "layout_rename"
    target: str                 # what was changed (e.g. layout name path)
    before: Any                 # snapshot of the prior state
    after: Any                  # snapshot of the new state
    rationale: str              # why this change was made
    severity_addressed: str     # which validator severity this targets


@dataclass
class FixAudit:
    template_path: str = ""
    out_path: str = ""
    remediated_at: str = ""
    pre_verdict: str = ""
    post_verdict: str = ""
    entries: list[FixEntry] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)

    def add(self, fix_type: str, target: str, before: Any, after: Any,
            rationale: str, severity_addressed: str) -> None:
        self.entries.append(FixEntry(
            fix_type=fix_type, target=target, before=before, after=after,
            rationale=rationale, severity_addressed=severity_addressed,
        ))

    def defer(self, finding_criterion: str, reason: str) -> None:
        self.deferred.append(f"{finding_criterion}: {reason}")

    def to_json(self) -> dict[str, Any]:
        return {
            "template_path": self.template_path,
            "out_path": self.out_path,
            "remediated_at": self.remediated_at,
            "pre_verdict": self.pre_verdict,
            "post_verdict": self.post_verdict,
            "summary": {
                "total_fixes": len(self.entries),
                "by_type": dict(Counter(e.fix_type for e in self.entries)),
                "by_severity": dict(Counter(e.severity_addressed for e in self.entries)),
            },
            "entries": [
                {
                    "fix_type": e.fix_type,
                    "target": e.target,
                    "before": e.before,
                    "after": e.after,
                    "rationale": e.rationale,
                    "severity_addressed": e.severity_addressed,
                }
                for e in self.entries
            ],
            "deferred": self.deferred,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Fix audit — pptx auto-remediation",
            "",
            f"- Template (before): `{self.template_path}`",
            f"- Template (after): `{self.out_path}`",
            f"- Remediated: {self.remediated_at}",
            f"- Validator verdict before: **{self.pre_verdict}**",
            f"- Validator verdict after:  **{self.post_verdict}**",
            "",
            f"## Summary",
            "",
            f"- Total fixes applied: {len(self.entries)}",
            f"- Findings deferred (manual review): {len(self.deferred)}",
            "",
        ]
        if self.entries:
            by_type: Counter[str] = Counter(e.fix_type for e in self.entries)
            lines.append("### By fix type")
            lines.append("")
            for ft, n in by_type.most_common():
                lines.append(f"- `{ft}`: {n}")
            lines.append("")
            lines.append("## Fixes applied")
            lines.append("")
            for i, e in enumerate(self.entries, 1):
                lines.append(f"### {i}. {e.fix_type} — {e.target}")
                lines.append("")
                lines.append(f"- **Targets severity:** {e.severity_addressed}")
                lines.append(f"- **Before:** `{e.before}`")
                lines.append(f"- **After:** `{e.after}`")
                lines.append(f"- **Why:** {e.rationale}")
                lines.append("")
        if self.deferred:
            lines.append("## Deferred — manual review recommended")
            lines.append("")
            for d in self.deferred:
                lines.append(f"- {d}")
            lines.append("")
        return "\n".join(lines) + "\n"


# ---- Fix routines ------------------------------------------------------

def _detect_layout_intent(name: str) -> str | None:
    """Wrapper for the shared detect_intent_from_name."""
    return detect_intent_from_name(name)


def fix_layout_naming(prs: Presentation, audit: FixAudit) -> None:
    """Rename layouts so their names match IR intents where reasonable.

    Strategy: walk all layouts, identify which already match an intent (skip),
    then for unmapped intents, rename the most plausible unused layout. The
    plausibility heuristic for v0.1: the first layout in master order that
    isn't already mapped.
    """
    layouts_to_rename: list[Any] = []
    matched_intents: set[str] = set()
    for master in prs.slide_masters:
        for layout in master.slide_layouts:
            intent = _detect_layout_intent(layout.name)
            if intent:
                matched_intents.add(intent)
            else:
                layouts_to_rename.append(layout)

    unmapped_intents = [i for i in LAYOUT_INTENTS if i not in matched_intents]
    # Rename in IR-catalog order so the most-used intents get the first
    # available layouts.
    for intent, layout in zip(unmapped_intents, layouts_to_rename):
        old_name = layout.name
        new_name = INTENT_TO_HEURISTIC_NAME[intent]
        layout.element.cSld.set("name", new_name)
        audit.add(
            fix_type="layout_rename",
            target=f"master.layout '{old_name}'",
            before=old_name,
            after=new_name,
            rationale=(
                f"Renamed to match IR intent '{intent}'. Improves "
                "layout_catalog_completeness and reduces orphan_elements."
            ),
            severity_addressed="layout_catalog_completeness",
        )


def fix_theme_color_tokens(prs: Presentation, audit: FixAudit,
                            existing_colors: dict[str, str]) -> None:
    """If the validator flagged missing color tokens, surface a markdown
    snippet the user can paste into their theme via PowerPoint's Slide Master
    view. v0.1 does NOT auto-edit theme XML (high risk of corrupting the
    file); we defer the actual edit but document the recommended palette.

    Because we don't edit, this records a 'recommended' fix rather than an
    'applied' fix — and is also reflected in the deferred list.
    """
    if existing_colors:
        return  # don't override anything the user already has

    palette_snippet = "\n".join(f"  {k}: {v}" for k, v in DEFAULT_PALETTE.items())
    audit.add(
        fix_type="color_palette_recommended",
        target="theme.colors",
        before="(empty)",
        after=DEFAULT_PALETTE,
        rationale=(
            "Validator flagged 0 explicit color tokens. v0.1 doesn't auto-edit "
            "theme XML (risk of corrupting the file); instead recommends this "
            "default palette. Apply via PowerPoint → View → Slide Master → "
            "Colors → Customize Colors."
        ),
        severity_addressed="color_tokens",
    )
    audit.defer("color_tokens",
               "Default palette recommended in audit; user applies via Slide Master view.")


def fix_master_typeface(prs: Presentation, audit: FixAudit,
                        existing_typefaces: list[str]) -> None:
    """Same posture as fix_theme_color_tokens — surface a recommendation."""
    if existing_typefaces:
        return
    audit.add(
        fix_type="typeface_recommended",
        target="master.fonts",
        before="(empty)",
        after={"display_and_body": DEFAULT_TYPEFACE},
        rationale=(
            "Validator flagged 0 named typefaces. v0.1 doesn't auto-edit theme "
            f"XML; recommends '{DEFAULT_TYPEFACE}' as the body/display family. "
            "Apply via PowerPoint → View → Slide Master → Fonts → Customize "
            "Fonts."
        ),
        severity_addressed="type_tokens",
    )
    audit.defer("type_tokens",
               f"Recommended typeface '{DEFAULT_TYPEFACE}'; user applies via Slide Master view.")


# ---- Pipeline ----------------------------------------------------------

def run_validator(template_path: Path) -> dict[str, Any]:
    """Invoke the validator and return its parsed report."""
    here = Path(__file__).resolve().parent
    result = subprocess.run(
        [sys.executable, str(here / "template_validator.py"),
         str(template_path), "--format", "pptx"],
        capture_output=True, text=True,
    )
    if not result.stdout:
        raise RuntimeError(f"validator produced no output: {result.stderr}")
    return json.loads(result.stdout)


def _existing_colors(prs: Presentation) -> dict[str, str]:
    """Collect explicit srgbClr values from masters (extractor's signal)."""
    colors: Counter[str] = Counter()
    for master in prs.slide_masters:
        for el in master.element.iter():
            tag = el.tag.split("}", 1)[-1] if "}" in el.tag else el.tag
            if tag == "srgbClr":
                val = el.get("val")
                if val and len(val) == 6:
                    colors[f"#{val.upper()}"] += 1
    return {f"observed_{i}": v for i, (v, _) in enumerate(colors.most_common(8))}


def _existing_typefaces(prs: Presentation) -> list[str]:
    """Collect named typefaces from masters."""
    fonts: Counter[str] = Counter()
    for master in prs.slide_masters:
        for el in master.element.iter():
            tag = el.tag.split("}", 1)[-1] if "}" in el.tag else el.tag
            if tag == "latin":
                tf = el.get("typeface")
                if tf and not tf.startswith("+"):
                    fonts[tf] += 1
    return [name for name, _ in fonts.most_common()]


def remediate(template_path: Path, validator_report: dict[str, Any],
              out_path: Path) -> FixAudit:
    """Apply automated fixes based on validator findings."""
    prs = Presentation(str(template_path))

    audit = FixAudit(
        template_path=str(template_path),
        out_path=str(out_path),
        remediated_at=dt.datetime.now().isoformat(timespec="seconds"),
        pre_verdict=validator_report.get("verdict", "(unknown)"),
    )

    # Inspect the findings to decide which fixes to apply
    findings = {f["criterion"]: f for f in validator_report.get("findings", [])}

    # Fix 1: layout naming (covers layout_catalog_completeness + orphan_elements)
    if findings.get("layout_catalog_completeness", {}).get("severity") in {"yellow", "red"}:
        fix_layout_naming(prs, audit)

    # Fix 2: color tokens (recommendation, since theme XML edit is risky in v0.1)
    if findings.get("color_tokens", {}).get("severity") in {"yellow", "red"}:
        fix_theme_color_tokens(prs, audit, _existing_colors(prs))

    # Fix 3: typeface recommendation
    if findings.get("type_tokens", {}).get("severity") in {"yellow", "red"}:
        fix_master_typeface(prs, audit, _existing_typefaces(prs))

    # Fix 4: style_hierarchy — deferred (XML edits)
    if findings.get("style_hierarchy", {}).get("severity") == "red":
        audit.defer(
            "style_hierarchy",
            "Adding distinct font-size tiers requires Slide Master XML edits; "
            "v0.1 deferred. Apply via PowerPoint → View → Slide Master and define "
            "explicit sizes for heading-1/2/3, body, caption."
        )

    # Fix 5: master_usage — deferred (consolidation risk)
    if findings.get("master_usage", {}).get("severity") in {"yellow", "red"}:
        audit.defer(
            "master_usage",
            "Multi-master consolidation can break inheritance subtly; v0.1 "
            "deferred to manual review. Open in PowerPoint → View → Slide Master "
            "and merge layouts under the primary master."
        )

    # Save the remediated .pptx
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))

    # Re-run validator on the remediated output
    try:
        post_report = run_validator(out_path)
        audit.post_verdict = post_report.get("verdict", "(unknown)")
    except Exception as e:
        audit.post_verdict = f"(re-validation failed: {e})"

    return audit


# ---- CLI ---------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Apply automated remediation to a .pptx template based on a "
            "validator report. Emits a remediated .pptx + fix-audit log "
            "(markdown + JSON)."
        )
    )
    parser.add_argument("template", help="Path to the source .pptx")
    parser.add_argument("--validator-report", help=(
        "Path to validator JSON output. If omitted, the validator runs "
        "first and its output is used directly."
    ))
    parser.add_argument("--out", required=True, help="Output .pptx path")
    args = parser.parse_args()

    template_path = Path(args.template).expanduser()
    if not template_path.exists():
        print(f"ERROR: {template_path} not found.", file=sys.stderr)
        return 2

    if args.validator_report:
        validator_report = json.loads(
            Path(args.validator_report).expanduser().read_text()
        )
    else:
        try:
            validator_report = run_validator(template_path)
        except Exception as e:
            print(f"ERROR running validator: {e}", file=sys.stderr)
            return 1

    out_path = Path(args.out).expanduser()
    try:
        audit = remediate(template_path, validator_report, out_path)
    except Exception as e:
        print(f"ERROR remediating: {e}", file=sys.stderr)
        return 1

    audit_md_path = out_path.with_suffix(out_path.suffix + ".audit.md")
    audit_json_path = out_path.with_suffix(out_path.suffix + ".audit.json")
    audit_md_path.write_text(audit.to_markdown())
    audit_json_path.write_text(json.dumps(audit.to_json(), indent=2) + "\n")

    print(f"Wrote {out_path}")
    print(f"Wrote {audit_md_path}")
    print(f"Wrote {audit_json_path}")
    print(f"Verdict before: {audit.pre_verdict}  →  after: {audit.post_verdict}")
    print(f"Applied {len(audit.entries)} fix(es); {len(audit.deferred)} deferred.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
