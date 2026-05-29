# Review Notes

## High-priority risks found in the original workspace

1. The original root `.env` contained a live OpenAI API key and Neo4j password.
2. The original workspace root was not a Git repository, so there was no existing repo hygiene or ignore policy at the root level.
3. Historical generated artifacts originally contained many machine-specific absolute paths and Neo4j connection references.
4. The original workspace did not include a single canonical dependency manifest for the Python backend and evaluation scripts.

## What this clean copy improves

- secrets are not copied
- `.env.example` was added
- `.gitignore` was added
- `requirements.txt` was added
- caches and obviously outdated folders were excluded
- machine-specific path strings were sanitized for the public copy
- environment-specific load manifests and run logs were removed

## Remaining manual decisions

- Decide whether all of `graph_rag_knowledgement` should be committed or reduced further for repo size.
- Decide whether `project/generated_v6_case_scenario_eval` should be tracked fully or split into `data/` and `reports/`.
