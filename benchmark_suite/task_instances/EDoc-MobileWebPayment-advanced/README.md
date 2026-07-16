# Task Review Card Hook

This task instance has a human-readable `case_review.json` used by the PaySkills Task Review page.

When modifying this task instance, update `case_review.json` in the same change if you alter:
- user scenario, turns, inputs, or initial state
- expected agent behavior
- rubric meaning, deterministic evaluation, LLM-assisted evaluation, or judge prompts
- fixture, replay, adapter, or environment behavior that affects scoring

`case_review.json` is only a review aid for humans. It must not be used by `task/run.sh`,
`evaluation/evaluate.sh`, or any scoring logic.
