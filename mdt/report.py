"""mdt.report — turn audit results into something a human will read."""

from __future__ import annotations

from typing import Any, Dict, List

from .core import AuditResult

_GLYPH = {
    "PASS": "ok  ",
    "CONSTANT": "FAIL",
    "IDENTITY": "FAIL",
    "BARE_ZERO": "FAIL",
    "LIVENESS_BIT": "FAIL",
    "DEAD_GATE": "FAIL",
}


def render_text(results: List[AuditResult], title: str = "discriminability audit") -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append(title)
    lines.append("=" * 72)
    failed = 0
    for r in results:
        mark = "ok  " if r.ok else "FAIL"
        if not r.ok:
            failed += 1
        lines.append("")
        lines.append(f"[{mark}] {r.subject}  ({r.n_samples} samples)")
        for f in r.findings:
            lines.append(f"       - {f.verdict}: {f.detail}")
        if r.stats:
            keep = {
                k: v
                for k, v in r.stats.items()
                if k not in ("pairs", "value_counts") and isinstance(v, (int, float, str))
            }
            if keep:
                lines.append("       stats: " + ", ".join(f"{k}={v}" for k, v in keep.items()))
    lines.append("")
    lines.append("-" * 72)
    lines.append(f"{len(results) - failed}/{len(results)} subjects clean, {failed} flagged")
    lines.append("-" * 72)
    return "\n".join(lines)


def render_markdown(
    results: List[AuditResult],
    title: str = "Discriminability audit",
    level: int = 1,
) -> str:
    """Render results as markdown. `level` picks the heading depth, so a case
    study can nest this under its own sections instead of hijacking h1."""
    h = "#" * max(1, min(level, 6))
    out: List[str] = [f"{h} {title}", ""]
    out.append("| subject | n | verdict |")
    out.append("|---|---:|---|")
    for r in results:
        out.append(f"| `{r.subject}` | {r.n_samples:,} | {'; '.join(r.verdicts) if not r.ok else 'PASS'} |")
    out.append("")
    findings = [f for r in results for f in r.findings]
    if findings:
        out.append(f"{h}# Findings")
        out.append("")
        for f in findings:
            out.append(f"{h}## `{f.subject}` — {f.verdict}")
            out.append("")
            out.append(f.detail)
            out.append("")
    return "\n".join(out)


def to_dicts(results: List[AuditResult]) -> List[Dict[str, Any]]:
    return [r.to_dict() for r in results]
