"""greencheck — discriminability testing for self-reported metrics."""

from .core import (
    ALL_VERDICTS,
    BARE_ZERO,
    CONSTANT,
    DEAD_GATE,
    IDENTITY,
    LIVENESS_BIT,
    NO_DATA,
    PASS,
    AuditResult,
    Finding,
    ProbePair,
    audit_gate,
    audit_gate_counts,
    audit_ledger,
    discriminate,
    get_path,
    load_jsonl,
)

def _resolve_version() -> str:
    """Single source of truth for the version: pyproject.toml.

    A second copy hardcoded here would drift from it sooner or later, and a
    package that reports a version different from the one it was built as is
    exactly the failure this whole tool is about. So there is one copy.
    """
    try:  # installed: read back the metadata the installer wrote
        from importlib.metadata import version as _dist_version

        return _dist_version("greencheck")
    except Exception:
        pass
    try:  # running from a source checkout
        import pathlib
        import re

        pyproject = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"
        m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "0.0.0+unknown"


__version__ = _resolve_version()

__all__ = [
    "ALL_VERDICTS",
    "BARE_ZERO",
    "CONSTANT",
    "DEAD_GATE",
    "IDENTITY",
    "LIVENESS_BIT",
    "NO_DATA",
    "PASS",
    "AuditResult",
    "Finding",
    "ProbePair",
    "audit_gate",
    "audit_gate_counts",
    "audit_ledger",
    "discriminate",
    "get_path",
    "load_jsonl",
    "__version__",
]
