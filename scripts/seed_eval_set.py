"""Seeds a small labeled eval set (intent -> known-good diff) so the
validator's LLM-judge and confidence score can be calibrated against
ground truth before you trust it in the guardrail. Start with 20-30
examples pulled from real merged PRs in the target repo.
"""

# TODO: load labeled examples, run them through /generate + /validate,
# and report how well confidence tracks actual merge-worthiness.
