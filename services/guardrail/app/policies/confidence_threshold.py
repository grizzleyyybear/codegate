"""Single tunable knob for how aggressive auto-merge is. Start
conservative; loosen once the validator's confidence score is shown to
track actual merge-worthiness (track this in the Grafana dashboard)."""

AUTO_MERGE_THRESHOLD = 0.85
REJECT_THRESHOLD = 0.35  # below this, don't even queue for human review
