"""
story_from_transcript.py — analyze a transcript and surface structured
candidates (throughline, beats, quotes, metrics) for the story-from-transcript
skill's conversational pass.

The skill itself runs in chat; this adapter does the mechanical analysis
work that's cheaper offline than in an LLM call.

Output:
    {
        "n_words": int,
        "throughline_candidates": [str, ...],     # top 3 candidate one-liners
        "beat_segments": [
            {"beat": "hook", "text": "...", "n_chars": int},
            {"beat": "context", "text": "...", "n_chars": int},
            ...
        ],
        "metrics": [{"value": "47%", "context": "..."}, ...],
        "quotes": [{"text": "...", "attribution_hint": "..."}, ...],
        "evidence_anchor_recommendation": "numbers" | "story" | "demo" | "framework" | "hybrid"
    }

Anonymity: ships in the public plugin. Heuristic only — no LLM calls; no
network. Processes the user's transcript locally.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _common import BEATS  # noqa: E402


# ============================================================================
# Throughline candidate extraction
# ============================================================================

_CLAIM_KEYWORDS = (
    "will", "must", "should", "is", "becomes", "wins", "drives", "makes",
    "needs to", "has to", "ought to", "cannot", "can't",
)


def _looks_like_claim(sentence: str) -> bool:
    lower = sentence.lower()
    return any(f" {kw} " in lower or lower.startswith(kw + " ") for kw in _CLAIM_KEYWORDS)


def _sentences(text: str) -> list[str]:
    # Naive split — works well enough for transcript prose.
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def throughline_candidates(text: str, n: int = 3) -> list[str]:
    """Surface the top-N claim-shaped sentences as throughline candidates."""
    candidates: list[tuple[int, str]] = []
    for s in _sentences(text):
        if len(s) < 30 or len(s) > 200:
            continue
        if not _looks_like_claim(s):
            continue
        # Score: prefer mid-length, claim-rich sentences with a noun phrase
        score = len(s)
        if any(kw in s.lower() for kw in ("our", "we", "you", "the next", "the future")):
            score += 20
        candidates.append((score, s))
    candidates.sort(reverse=True, key=lambda t: t[0])
    return [c[1] for c in candidates[:n]]


# ============================================================================
# Beat segmentation
# ============================================================================

# Cluster paragraphs into beat-buckets by relative position. Position-based
# segmentation is the v0.1 heuristic; v0.2 can move to semantic clustering.

_BEAT_POSITION_BUCKETS = [
    (0.00, 0.05, "hook"),
    (0.05, 0.20, "context"),
    (0.20, 0.35, "problem"),
    (0.35, 0.45, "claim"),
    (0.45, 0.70, "evidence"),
    (0.70, 0.85, "tension"),
    (0.85, 0.95, "resolution"),
    (0.95, 1.00, "next"),
]


def beat_segments(text: str) -> list[dict[str, Any]]:
    """Cluster paragraphs into beat-bucket segments."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return []
    total = len(paras)
    buckets: dict[str, list[str]] = {b: [] for b in BEATS}
    for i, p in enumerate(paras):
        pos = i / max(1, total - 1)
        for lo, hi, beat in _BEAT_POSITION_BUCKETS:
            if lo <= pos < hi or (hi == 1.00 and pos == 1.0):
                buckets[beat].append(p)
                break
    segments: list[dict[str, Any]] = []
    for beat in BEATS:
        if not buckets[beat]:
            continue
        combined = "\n\n".join(buckets[beat])
        segments.append({
            "beat": beat,
            "text": combined,
            "n_chars": len(combined),
            "n_paragraphs": len(buckets[beat]),
        })
    return segments


# ============================================================================
# Metric extraction
# ============================================================================

_METRIC_RE = re.compile(
    r"(?<!\w)(\$?\d[\d,]*(?:\.\d+)?\s*(?:%|x|×|k|m|b|bn|million|billion|days?|years?|weeks?|months?|hours?|users|customers|deals|points?))(?!\w)",
    re.IGNORECASE,
)


def extract_metrics(text: str) -> list[dict[str, str]]:
    """Find quantitative claims with their surrounding context."""
    out: list[dict[str, str]] = []
    for m in _METRIC_RE.finditer(text):
        value = m.group(0)
        start = max(0, m.start() - 80)
        end = min(len(text), m.end() + 80)
        context = text[start:end].strip()
        out.append({"value": value.strip(), "context": context})
    # Dedupe on (value, leading context word)
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for item in out:
        key = (item["value"], item["context"][:30])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:20]


# ============================================================================
# Quote extraction
# ============================================================================

_QUOTE_RE = re.compile(r'["“]([^"”]{20,300})["”]')


def extract_quotes(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in _QUOTE_RE.finditer(text):
        quote = m.group(1).strip()
        # Look for an attribution within ~60 chars after the quote
        tail = text[m.end():m.end() + 80]
        attribution = ""
        attr_match = re.search(r"\b(said|noted|wrote|put it)\s+([A-Z][\w\s.,-]{2,60})", tail)
        if attr_match:
            attribution = attr_match.group(2).strip().strip(".,")
        out.append({"text": quote, "attribution_hint": attribution})
    return out[:10]


# ============================================================================
# Evidence anchor recommendation
# ============================================================================

def recommend_evidence_anchor(metrics: list[dict], quotes: list[dict],
                              n_words: int) -> str:
    n_m = len(metrics)
    n_q = len(quotes)
    framework_words = ("framework", "model", "system", "principle", "thesis")
    framework_signal = sum(1 for w in framework_words if w in " ".join(
        m.get("context", "") for m in metrics).lower())

    if n_m >= 4 and n_m > n_q:
        return "numbers"
    if n_q >= 3 and n_q > n_m:
        return "story"
    if framework_signal >= 2:
        return "framework"
    if n_m == 0 and n_q == 0:
        return "story"  # default for prose-heavy with no anchors
    return "hybrid"


# ============================================================================
# Pipeline
# ============================================================================

def analyze(text: str) -> dict[str, Any]:
    metrics = extract_metrics(text)
    quotes = extract_quotes(text)
    return {
        "n_words": len(text.split()),
        "throughline_candidates": throughline_candidates(text),
        "beat_segments": beat_segments(text),
        "metrics": metrics,
        "quotes": quotes,
        "evidence_anchor_recommendation": recommend_evidence_anchor(
            metrics, quotes, len(text.split())
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze a transcript and emit structured candidates "
                    "(throughline, beats, metrics, quotes) for the "
                    "story-from-transcript conversational skill."
    )
    parser.add_argument("transcript", nargs="?", default="-",
                        help="Path to transcript text file (default: stdin)")
    parser.add_argument("--out", help="Output JSON path (default: stdout)")
    args = parser.parse_args()

    if args.transcript == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.transcript).expanduser().read_text()

    if not text.strip():
        print("ERROR: empty transcript.", file=sys.stderr)
        return 1
    if len(text.split()) < 100:
        print("WARNING: transcript is < 100 words. Heuristics work best on "
              "longer source material.", file=sys.stderr)

    result = analyze(text)
    out_text = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).expanduser().write_text(out_text + "\n")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
