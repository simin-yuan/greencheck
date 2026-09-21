"""mdt — discriminability testing for self-reported metrics."""

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

__version__ = "0.1.0"

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
