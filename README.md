# Industrial Safety Law Graph-RAG System

This repository is a public-safe copy of the current industrial safety law Graph-RAG workspace.

## Included

- `app/graph_rag_pipeline`: current read-only Graph-RAG backend and smoke tests
- `project/raw_cases`: current case source set used by the v6 workflow
- `project/generated_v6_case_scenario_eval`: current v6 evaluation outputs
- `project/*.py`: current v6-oriented evaluation and reporting scripts
- `graph_rag_knowledgement`: current knowledge-graph artifacts, selected reports, and supporting data

## Excluded

- root `.env` with live secrets
- logs
- zip backups
- legacy archive folders
- v4 and v5 generated experiment folders
- frontend reference copy
- Python cache folders

## Run Notes

- Set environment variables from `.env.example` before running backend or evaluation scripts.
- The backend entrypoint is `app/graph_rag_pipeline/ask_adapter.py`.
- Example local run:

```bash
python -m uvicorn graph_rag_pipeline.ask_adapter:app --app-dir app --host 127.0.0.1 --port 8000
```

## Public-safe cleanup

- Live secrets and the original root `.env` are excluded.
- Historical manifests and environment-specific run logs were removed.
- Remaining text artifacts were sanitized to avoid machine-specific absolute paths.
- Dependency management files were added manually because the original workspace did not contain a single canonical Python package manifest.
