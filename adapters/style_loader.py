"""
style_loader.py — load a storytelling style by name, resolve `extends:`
chain, and respect user-style precedence over plugin-shipped styles.

A storytelling style is a YAML file conforming to `styles/schema.json`.
Styles can live in two places:

    Plugin-shipped:   <plugin-root>/styles/<name>.yaml
    User-authored:    ~/.cowork/plugins/slide-publisher/styles/<name>.yaml

User-authored styles win over plugin-shipped styles of the same name.

Inheritance: a style may set `extends: <parent-name>`. The loader merges
parent-then-child (child keys override parent keys; nested dicts merge,
arrays replace).

Anonymity: ships in the public plugin. No user-specific defaults.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required. pip install pyyaml", file=sys.stderr)
    sys.exit(2)

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None  # type: ignore


PLUGIN_STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"
USER_STYLES_DIR = Path.home() / ".cowork" / "plugins" / "slide-publisher" / "styles"


def _candidate_paths(name: str) -> list[Path]:
    """User-style path first (precedence), then plugin-shipped."""
    return [
        USER_STYLES_DIR / f"{name}.yaml",
        PLUGIN_STYLES_DIR / f"{name}.yaml",
    ]


def _read_one(name: str) -> dict[str, Any]:
    """Read a single style file by name. Raises FileNotFoundError if missing."""
    for path in _candidate_paths(name):
        if path.exists():
            return yaml.safe_load(path.read_text())
    raise FileNotFoundError(
        f"style '{name}' not found. Looked in:\n  "
        + "\n  ".join(str(p) for p in _candidate_paths(name))
    )


def _deep_merge(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """Child keys override parent keys. Nested dicts merge. Arrays replace."""
    out: dict[str, Any] = dict(parent)
    for k, v in child.items():
        if (
            k in out
            and isinstance(out[k], dict)
            and isinstance(v, dict)
        ):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(name: str, *, max_chain: int = 5) -> dict[str, Any]:
    """Load a style by name with full inheritance resolution.

    Raises FileNotFoundError if any style in the chain is missing, or
    ValueError on circular inheritance / chain too long.
    """
    chain: list[str] = []
    cursor: str | None = name
    docs: list[dict[str, Any]] = []
    while cursor is not None:
        if cursor in chain:
            raise ValueError(
                f"circular inheritance: {' → '.join(chain)} → {cursor}"
            )
        if len(chain) >= max_chain:
            raise ValueError(
                f"extends chain longer than {max_chain}: {' → '.join(chain)}"
            )
        chain.append(cursor)
        doc = _read_one(cursor)
        docs.append(doc)
        cursor = doc.get("extends")

    # Merge oldest ancestor first, then each child in reverse.
    docs.reverse()
    merged: dict[str, Any] = {}
    for d in docs:
        merged = _deep_merge(merged, d)
    # `extends` shouldn't appear in the resolved style — strip it
    merged.pop("extends", None)
    return merged


def list_available() -> list[dict[str, Any]]:
    """Enumerate available styles, user-styles overshadowing plugin-shipped."""
    seen: dict[str, dict[str, Any]] = {}
    # Plugin-shipped first
    if PLUGIN_STYLES_DIR.exists():
        for p in sorted(PLUGIN_STYLES_DIR.glob("*.yaml")):
            try:
                doc = yaml.safe_load(p.read_text())
                seen[p.stem] = {
                    "name": doc.get("name", p.stem),
                    "description": doc.get("description", "").strip().split("\n", 1)[0],
                    "authority": doc.get("authority", ""),
                    "source": "plugin",
                    "path": str(p),
                }
            except Exception:
                continue
    # User styles override
    if USER_STYLES_DIR.exists():
        for p in sorted(USER_STYLES_DIR.glob("*.yaml")):
            try:
                doc = yaml.safe_load(p.read_text())
                seen[p.stem] = {
                    "name": doc.get("name", p.stem),
                    "description": doc.get("description", "").strip().split("\n", 1)[0],
                    "authority": doc.get("authority", ""),
                    "source": "user",
                    "path": str(p),
                }
            except Exception:
                continue
    return list(seen.values())


def validate(name_or_path: str) -> tuple[bool, list[str]]:
    """Validate a style against the schema. Accepts name or filesystem path."""
    if Draft202012Validator is None:
        return False, ["jsonschema is not installed. pip install jsonschema"]
    schema_path = PLUGIN_STYLES_DIR / "schema.json"
    if not schema_path.exists():
        return False, [f"schema not found: {schema_path}"]
    schema = json.loads(schema_path.read_text())
    p = Path(name_or_path)
    if p.exists():
        doc = yaml.safe_load(p.read_text())
    else:
        try:
            doc = load(name_or_path)
        except Exception as e:
            return False, [str(e)]
    v = Draft202012Validator(schema)
    errs = sorted(v.iter_errors(doc), key=lambda e: list(e.path))
    if errs:
        return False, [f"{list(e.path)}: {e.message}" for e in errs]
    return True, []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load, list, or validate slide-publisher storytelling styles."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_load = sub.add_parser("load", help="Load + resolve a style; emit merged YAML")
    p_load.add_argument("name", help="Style name (e.g., 'ted-talk')")

    p_list = sub.add_parser("list", help="List available styles")
    p_list.add_argument("--format", choices=["text", "json"], default="text")

    p_validate = sub.add_parser("validate", help="Validate a style against the schema")
    p_validate.add_argument("name_or_path", help="Style name or .yaml path")

    args = parser.parse_args()

    if args.cmd == "load":
        try:
            merged = load(args.name)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))
        return 0

    if args.cmd == "list":
        styles = list_available()
        if args.format == "json":
            print(json.dumps(styles, indent=2))
        else:
            for s in styles:
                src = f"[{s['source']}]"
                auth = f" — {s['authority']}" if s["authority"] else ""
                print(f"  {src:>8} {s['name']:<35} {s['description'][:60]}{auth}")
        return 0

    if args.cmd == "validate":
        ok, errs = validate(args.name_or_path)
        if ok:
            print(f"OK   {args.name_or_path}")
            return 0
        print(f"FAIL {args.name_or_path}")
        for e in errs:
            print(f"  {e}")
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
