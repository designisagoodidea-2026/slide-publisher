"""
run_validation.py — process each validation case and land artifacts.

Does NOT score outputs. Scoring is the user's job per EXPECTED.md per case.

Per case, dispatches on the case's INPUT-spec.md `pipeline` field
(controlling which stages run). Outputs land in the case folder.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = PLUGIN_ROOT / "adapters"
CASES_DIR = Path(__file__).resolve().parent / "cases"


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True,
                           cwd=str(cwd) if cwd else None)
    return proc.returncode, proc.stdout, proc.stderr


def find_input(case_dir: Path) -> Path | None:
    for cand in ["input.pptx", "input.yaml", "input.json"]:
        p = case_dir / cand
        if p.exists():
            return p
    return None


def process_pptx_case(case_dir: Path, fmt_hint: str = "pptx") -> dict[str, Any]:
    """Standard pipeline for a pptx input case."""
    log: dict[str, Any] = {"case": case_dir.name, "stages": {}}
    input_path = case_dir / "input.pptx"
    if not input_path.exists():
        log["error"] = "input.pptx missing"
        return log

    # 1. Classifier
    rc, out, err = run([sys.executable, str(ADAPTERS / "template_classifier.py"),
                        str(input_path)])
    (case_dir / "01-classifier.json").write_text(out or err or "")
    log["stages"]["classifier"] = {"exit": rc}

    classifier_data = json.loads(out) if out else {}
    classification = classifier_data.get("classification", "unknown")

    # 2. Synthesizer (only if deck-with-implicit-pattern)
    synth_path = case_dir / "S-synthesized.pptx"
    if classification == "deck-with-implicit-pattern":
        rc, out, err = run([
            sys.executable, str(ADAPTERS / "template_synthesizer_pptx.py"),
            str(input_path), "--out", str(synth_path),
            "--report", str(case_dir / "02-synthesizer-report.json"),
        ])
        log["stages"]["synthesizer"] = {"exit": rc}
        extract_target = synth_path
    else:
        extract_target = input_path
        log["stages"]["synthesizer"] = {"skipped": "classification != deck-with-implicit-pattern"}

    # 3. Extractor
    rc, out, err = run([sys.executable, str(ADAPTERS / "template_extractor_pptx.py"),
                        str(extract_target)])
    (case_dir / "03-extractor.json").write_text(out or err or "")
    log["stages"]["extractor"] = {"exit": rc, "target": str(extract_target)}

    # 4. Validator
    rc, out, err = run([sys.executable, str(ADAPTERS / "template_validator.py"),
                        str(extract_target), "--format", fmt_hint])
    (case_dir / "04-validator.json").write_text(out or err or "")
    log["stages"]["validator"] = {"exit": rc}

    validator_data = json.loads(out) if out else {}
    verdict = validator_data.get("verdict", "unknown")

    # 5. Remediator (only if warn/fail)
    if verdict in {"warn", "fail"}:
        remediated = case_dir / "R-remediated.pptx"
        rc, out, err = run([
            sys.executable, str(ADAPTERS / "remediation_apply_pptx.py"),
            str(extract_target),
            "--validator-report", str(case_dir / "04-validator.json"),
            "--out", str(remediated),
        ])
        log["stages"]["remediator"] = {"exit": rc}
    else:
        log["stages"]["remediator"] = {"skipped": f"verdict={verdict}"}

    # 6. Renderer (skip for empty templates)
    if extract_target.exists() and classification != "empty":
        # Build profile from extractor output
        ext_data = json.loads((case_dir / "03-extractor.json").read_text() or "{}")
        if ext_data.get("layout_map"):
            import yaml
            profile = {
                "profile_version": "1.0.0",
                "preferred_output": "pptx",
                "templates": {"pptx": {
                    "path": str(extract_target),
                    "layout_map": ext_data["layout_map"],
                    "quality_score": ext_data.get("quality_score", 0),
                }},
                "style_tokens": ext_data.get("style_tokens", {}),
                "setup_completed": "2026-06-01",
                "setup_version": "0.1.0-pre",
            }
            profile_path = case_dir / "profile.yaml"
            profile_path.write_text(yaml.safe_dump(profile, sort_keys=False))
            render_out = case_dir / "06-render.pptx"
            # Use a generic IR for rendering
            ir_path = PLUGIN_ROOT / "ir/examples/design-system-retro.yaml"
            rc, out, err = run([
                sys.executable, str(ADAPTERS / "pptx_renderer.py"),
                "--ir", str(ir_path),
                "--profile", str(profile_path),
                "--out", str(render_out),
            ])
            log["stages"]["renderer"] = {"exit": rc}

    return log


def process_ir_case(case_dir: Path) -> dict[str, Any]:
    """Standard pipeline for an IR-only case (cases 7, 8)."""
    log: dict[str, Any] = {"case": case_dir.name, "stages": {}}
    ir_path = case_dir / "input.yaml"
    if not ir_path.exists():
        log["error"] = "input.yaml missing"
        return log

    # Validator (slide-ir-validator) — for v0.1 we use the schema directly
    import yaml, jsonschema
    schema_path = PLUGIN_ROOT / "ir/schema.json"
    schema = json.loads(schema_path.read_text())
    ir = yaml.safe_load(ir_path.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(ir),
                    key=lambda e: list(e.path))
    validator_report = {
        "format": "ir",
        "schema_valid": len(errors) == 0,
        "errors": [{"path": list(e.path), "message": e.message} for e in errors],
    }
    (case_dir / "04-validator.json").write_text(json.dumps(validator_report, indent=2))
    log["stages"]["validator"] = {"schema_valid": validator_report["schema_valid"]}

    if not validator_report["schema_valid"]:
        log["stages"]["renderer"] = {"skipped": "IR failed schema; renderer would refuse"}
        return log

    # Renderer (against a default profile from synthetic-template fixture)
    profile = {
        "profile_version": "1.0.0",
        "preferred_output": "pptx",
        "templates": {"pptx": {
            "path": str(PLUGIN_ROOT / "tests/fixtures/synthetic-template.pptx"),
            "layout_map": {
                "title": "Title Slide", "section_break": "Section Header",
                "claim_with_evidence": "Title and Content",
                "three_pillars": "Three Column", "comparison": "Comparison",
                "quote": "Pull Quote", "image_with_caption": "Image and Caption",
                "metrics": "Stat Block", "timeline": "Timeline",
                "callout": "Big Statement",
            },
            "quality_score": 70,
        }},
        "style_tokens": {},
        "setup_completed": "2026-06-01",
        "setup_version": "0.1.0-pre",
    }
    profile_path = case_dir / "profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False))
    render_out = case_dir / "06-render.pptx"
    rc, out, err = run([
        sys.executable, str(ADAPTERS / "pptx_renderer.py"),
        "--ir", str(ir_path), "--profile", str(profile_path),
        "--out", str(render_out),
    ])
    log["stages"]["renderer"] = {"exit": rc}
    return log


def main() -> int:
    if not CASES_DIR.exists():
        print(f"No cases directory: {CASES_DIR}", file=sys.stderr)
        return 1
    case_dirs = sorted([d for d in CASES_DIR.iterdir() if d.is_dir()])
    if not case_dirs:
        print(f"No cases in {CASES_DIR}", file=sys.stderr)
        return 1

    logs = []
    for case_dir in case_dirs:
        print(f"\n=== {case_dir.name} ===")
        # Dispatch based on input filename
        if (case_dir / "input.pptx").exists():
            log = process_pptx_case(case_dir)
        elif (case_dir / "input.yaml").exists():
            log = process_ir_case(case_dir)
        else:
            log = {"case": case_dir.name, "error": "no recognized input file"}
        logs.append(log)
        for stage, info in log.get("stages", {}).items():
            print(f"  {stage}: {info}")

    # Aggregate log
    (CASES_DIR / "_run-summary.json").write_text(
        json.dumps({"cases": logs}, indent=2) + "\n"
    )
    print(f"\nWrote {CASES_DIR / '_run-summary.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
