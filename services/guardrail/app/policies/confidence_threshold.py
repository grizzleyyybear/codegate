"""Tunable knobs for how autonomous the pipeline is. All env-driven so
the same build can run fully-gated (defaults) or near-fully-autonomous
without a code change.

Start conservative; loosen once the validator's confidence score is
shown to track actual merge-worthiness (track this in Grafana).

Full-autonomy example (.env):
    AUTO_MERGE_THRESHOLD=0.5
    REJECT_THRESHOLD=0.0
    ENFORCE_SENSITIVE_PATHS=false
    MAX_CODEGEN_ATTEMPTS=10   # (gateway) effectively unbounded
"""
import os

AUTO_MERGE_THRESHOLD = float(os.environ.get("AUTO_MERGE_THRESHOLD", "0.85"))
REJECT_THRESHOLD = float(os.environ.get("REJECT_THRESHOLD", "0.35"))
