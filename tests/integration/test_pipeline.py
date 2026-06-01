"""
test_pipeline.py — end-to-end integration test for slide-publisher.

Exercises the full pipeline against the two synthetic fixtures and asserts
the outcome at every stage. Used as a regression-detector and as a worked
example of how the skills compose.

Run from the plugin root:

    cd "<plugin-root>"
    python tests/integration/test_pipeline.py

Exit 0 = all assertions pass. Non-zero = regression; the failing stage is
printed.

Requires: python-pptx, pyyaml, jsonschema. The plugin's normal runtime
dependencies.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = PLUGIN_ROOT / "adapters"
FIXTURES = PLUGIN_ROOT / "tests" / "fixtures"
OUT_DIR = Path("/tmp/slide-publisher-integration")


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str = ""
    duration_ms: int = 0


@dataclass
class TestRun:
    results: list[TestResult] = field(default_factory=list)

    def add(self, result: TestResult) -> None:
        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {result.name} ({result.duration_ms} ms)")
        if not result.passed and result.message:
            print(f"         {result.message}")

    def summary(self) -> int:
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        print()
        print(f"Summary: {passed}/{total} passed.")
        if passed < total:
            print("FAILED tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")
            return 1
        return 0


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PLUGIN_ROOT))
    return proc.returncode, proc.stdout, proc.stderr


def time_ms(start: float) -> int:
    import time
    return int((time.perf_counter() - start) * 1000)


# ---------------------------------------------------------------------------
# Stage assertions
# ---------------------------------------------------------------------------

def assert_classifier_template(run: TestRun) -> None:
    import time
    t = time.perf_counter()
    rc, out, err = run_cmd([
        sys.executable, str(ADAPTERS / "template_classifier.py"),
        str(FIXTURES / "synthetic-template.pptx"),
    ])
    if rc != 0:
        run.add(TestResult("classifier_on_template", False,
                           f"exit {rc}: {err}", time_ms(t)))
        return
    data = json.loads(out)
    ok = data["classification"] == "template"
    run.add(TestResult(
        "classifier_on_template",
        ok,
        "" if ok else f"expected 'template', got '{data['classification']}'",
        time_ms(t),
    ))


def assert_classifier_deck(run: TestRun) -> None:
    import time
    t = time.perf_counter()
    rc, out, err = run_cmd([
        sys.executable, str(ADAPTERS / "template_classifier.py"),
        str(FIXTURES / "synthetic-deck-no-template.pptx"),
    ])
    if rc != 0:
        run.add(TestResult("classifier_on_deck", False,
                           f"exit {rc}: {err}", time_ms(t)))
        return
    data = json.loads(out)
    ok = data["classification"] == "deck-with-implicit-pattern"
    run.add(TestResult(
        "classifier_on_deck",
        ok,
        "" if ok else f"expected 'deck-with-implicit-pattern', got '{data['classification']}'",
        time_ms(t),
    ))


def assert_synthesizer_pptx(run: TestRun) -> dict | None:
    import time
    t = time.perf_counter()
    synth_out = OUT_DIR / "synthesized-template.pptx"
    report_out = OUT_DIR / "synthesizer-report.json"
    synth_out.parent.mkdir(parents=True, exist_ok=True)
    rc, out, err = run_cmd([
        sys.executable, str(ADAPTERS / "template_synthesizer_pptx.py"),
        str(FIXTURES / "synthetic-deck-no-template.pptx"),
        "--out", str(synth_out),
        "--report", str(report_out),
    ])
    if rc != 0:
        run.add(TestResult("synthesizer_pptx", False,
                           f"exit {rc}: {err}", time_ms(t)))
        return None
    report = json.loads(report_out.read_text())
    expected_n_clusters = 4  # 4 patterns in the deck fixture
    expected_intents = {"title", "three_pillars", "metrics", "quote"}
    ok = (report["n_clusters"] == expected_n_clusters and
          set(report["suggested_layout_map"].keys()) == expected_intents)
    msg = ""
    if not ok:
        msg = (f"clusters={report['n_clusters']} (expected {expected_n_clusters}); "
               f"intents={set(report['suggested_layout_map'].keys())}")
    run.add(TestResult("synthesizer_pptx", ok, msg, time_ms(t)))
    return report if ok else None


def assert_extractor_pptx(run: TestRun, target: Path) -> dict | None:
    import time
    t = time.perf_counter()
    rc, out, err = run_cmd([
        sys.executable, str(ADAPTERS / "template_extractor_pptx.py"),
        "--strip-debug", str(target),
    ])
    if rc != 0:
        run.add(TestResult(f"extractor_pptx[{target.name}]", False,
                           f"exit {rc}: {err}", time_ms(t)))
        return None
    profile_entry = json.loads(out)
    ok = (
        "layout_map" in profile_entry and
        "quality_score" in profile_entry and
        0 <= profile_entry["quality_score"] <= 100
    )
    run.add(TestResult(
        f"extractor_pptx[{target.name}]", ok,
        "" if ok else f"missing fields or bad score",
        time_ms(t),
    ))
    return profile_entry if ok else None


def assert_validator_pptx(run: TestRun, target: Path) -> None:
    import time
    t = time.perf_counter()
    rc, out, err = run_cmd([
        sys.executable, str(ADAPTERS / "template_validator.py"),
        str(target), "--format", "pptx",
    ])
    # rc != 0 is acceptable (validator returns 1 on verdict=fail by design)
    if not out:
        run.add(TestResult(f"validator_pptx[{target.name}]", False,
                           f"no stdout (stderr: {err})", time_ms(t)))
        return
    report = json.loads(out)
    ok = (
        "verdict" in report and
        report["verdict"] in {"pass", "warn", "fail"} and
        len(report["findings"]) == 6  # six criteria
    )
    run.add(TestResult(
        f"validator_pptx[{target.name}]", ok,
        "" if ok else f"verdict={report.get('verdict')}, findings_count={len(report.get('findings', []))}",
        time_ms(t),
    ))


def assert_renderer_pptx(run: TestRun, profile: dict, ir_path: Path,
                          tag: str) -> Path | None:
    import time, yaml
    t = time.perf_counter()
    profile_path = OUT_DIR / f"profile-{tag}.yaml"
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False))
    out_pptx = OUT_DIR / f"rendered-{tag}.pptx"
    rc, out, err = run_cmd([
        sys.executable, str(ADAPTERS / "pptx_renderer.py"),
        "--ir", str(ir_path),
        "--profile", str(profile_path),
        "--out", str(out_pptx),
    ])
    if rc != 0:
        run.add(TestResult(f"renderer_pptx[{tag}]", False,
                           f"exit {rc}: {err}", time_ms(t)))
        return None

    # Re-open and assert slide count
    try:
        from pptx import Presentation
        prs = Presentation(str(out_pptx))
        expected_n = len(yaml.safe_load(ir_path.read_text())["slides"])
        ok = len(prs.slides) == expected_n
    except Exception as e:
        run.add(TestResult(f"renderer_pptx[{tag}]", False,
                           f"reopen failed: {e}", time_ms(t)))
        return None
    run.add(TestResult(
        f"renderer_pptx[{tag}]", ok,
        "" if ok else f"slide count mismatch",
        time_ms(t),
    ))
    return out_pptx if ok else None


def assert_loss_manifest_well_formed(run: TestRun, manifest_json_path: Path,
                                      tag: str) -> None:
    import time
    t = time.perf_counter()
    if not manifest_json_path.exists():
        run.add(TestResult(f"loss_manifest[{tag}]", False,
                           f"file missing", time_ms(t)))
        return
    data = json.loads(manifest_json_path.read_text())
    ok = (
        "summary" in data and
        all(k in data["summary"] for k in ["lossless", "lossy", "dropped", "annotated"]) and
        "entries" in data and
        isinstance(data["entries"], list) and
        len(data["entries"]) > 0
    )
    run.add(TestResult(
        f"loss_manifest[{tag}]", ok,
        "" if ok else "missing fields or empty entries",
        time_ms(t),
    ))


def assert_figma_synthesizer(run: TestRun) -> None:
    import time
    t = time.perf_counter()
    rc, out, err = run_cmd([
        sys.executable, str(ADAPTERS / "template_synthesizer_figma.py"),
        str(FIXTURES / "synthetic-figma-mcp-output.json"),
    ])
    if rc != 0:
        run.add(TestResult("synthesizer_figma", False,
                           f"exit {rc}: {err}", time_ms(t)))
        return
    # synthetic-figma-mcp-output.json is template-shaped, not deck-shaped.
    # The synthesizer will still cluster it (10 distinct templates → 10 clusters).
    # Assert the structure regardless.
    data = json.loads(out)
    ok = (
        "n_clusters" in data and
        "suggested_layout_map" in data and
        "mcp_creation_plan" in data
    )
    run.add(TestResult("synthesizer_figma", ok,
                       "" if ok else "missing fields", time_ms(t)))


def assert_figma_yaml_emitter(run: TestRun) -> None:
    import time, yaml
    t = time.perf_counter()
    profile_path = OUT_DIR / "figma-profile.yaml"
    profile = {
        "profile_version": "1.0.0",
        "preferred_output": "figma",
        "templates": {"figma": {
            "file_key": "TEST",
            "layout_map": {i: f"1:{100+j*10}" for j, i in enumerate([
                "title", "section_break", "claim_with_evidence", "three_pillars",
                "comparison", "quote", "image_with_caption", "metrics",
                "timeline", "callout",
            ])},
            "quality_score": 90,
        }},
        "style_tokens": {},
        "setup_completed": "2026-06-01",
        "setup_version": "0.1.0-pre",
    }
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False))
    out_yaml = OUT_DIR / "figma-rendered.yaml"
    rc, out, err = run_cmd([
        sys.executable, str(ADAPTERS / "figma_yaml_emitter.py"),
        "--ir", str(PLUGIN_ROOT / "ir/examples/design-system-retro.yaml"),
        "--profile", str(profile_path),
        "--out", str(out_yaml),
    ])
    if rc != 0:
        run.add(TestResult("figma_yaml_emitter", False,
                           f"exit {rc}: {err}", time_ms(t)))
        return
    envelope = yaml.safe_load(out_yaml.read_text())
    ok = (
        envelope.get("file_key") == "TEST" and
        len(envelope.get("slides", [])) == 10 and
        all("template_node_id" in s for s in envelope["slides"])
    )
    run.add(TestResult("figma_yaml_emitter", ok,
                       "" if ok else "envelope shape wrong", time_ms(t)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    run = TestRun()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("STAGE 1 — Classifier")
    print("=" * 60)
    assert_classifier_template(run)
    assert_classifier_deck(run)

    print()
    print("=" * 60)
    print("STAGE 2 — Synthesizer (deck → synthesized template)")
    print("=" * 60)
    synth_report = assert_synthesizer_pptx(run)
    assert_figma_synthesizer(run)

    print()
    print("=" * 60)
    print("STAGE 3 — Extractor (template → profile entry)")
    print("=" * 60)
    template_entry = assert_extractor_pptx(run, FIXTURES / "synthetic-template.pptx")
    synth_pptx = OUT_DIR / "synthesized-template.pptx"
    synth_entry = (assert_extractor_pptx(run, synth_pptx)
                   if synth_pptx.exists() else None)

    print()
    print("=" * 60)
    print("STAGE 4 — Validator")
    print("=" * 60)
    assert_validator_pptx(run, FIXTURES / "synthetic-template.pptx")
    if synth_pptx.exists():
        assert_validator_pptx(run, synth_pptx)

    print()
    print("=" * 60)
    print("STAGE 5 — Renderers")
    print("=" * 60)
    # render-pptx against the template fixture
    if template_entry:
        profile = _wrap_profile(template_entry, FIXTURES / "synthetic-template.pptx")
        rendered = assert_renderer_pptx(
            run, profile, PLUGIN_ROOT / "ir/examples/design-system-retro.yaml",
            "template-fixture",
        )
        if rendered:
            assert_loss_manifest_well_formed(
                run, Path(str(rendered) + ".loss.json"), "template-fixture",
            )
    # render-pptx against the synthesized template
    if synth_entry and synth_report:
        # Use the synthesizer's suggested layout_map (richer than the extractor's)
        merged_entry = {
            **synth_entry,
            "layout_map": synth_report["suggested_layout_map"],
        }
        profile = _wrap_profile(merged_entry, synth_pptx)
        rendered = assert_renderer_pptx(
            run, profile, PLUGIN_ROOT / "ir/examples/design-system-retro.yaml",
            "synth-template",
        )
        if rendered:
            assert_loss_manifest_well_formed(
                run, Path(str(rendered) + ".loss.json"), "synth-template",
            )

    # figma yaml emitter
    assert_figma_yaml_emitter(run)

    return run.summary()


def _wrap_profile(entry: dict, pptx_path: Path) -> dict:
    return {
        "profile_version": "1.0.0",
        "preferred_output": "pptx",
        "templates": {"pptx": {
            "path": str(pptx_path),
            "layout_map": entry.get("layout_map", {}),
            "quality_score": entry.get("quality_score", 0),
        }},
        "style_tokens": entry.get("style_tokens", {}),
        "setup_completed": "2026-06-01",
        "setup_version": "0.1.0-pre",
    }


if __name__ == "__main__":
    sys.exit(main())
