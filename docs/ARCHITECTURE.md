# Project Architecture

One FastAPI process serves two independent feature groups. `app/main.py` is the recommended entrypoint and combines both groups without mixing their storage.

```text
app/main.py
|-- graph_rag_pipeline/  Law questions and legal evidence
|   `-- Neo4j (law graph only)
`-- operations_api/     Equipment, watch, attendance, alerts, dashboard
    `-- data/watch_data.db (SQLite only)
```

## Ownership

- Graph-RAG developers: `app/graph_rag_pipeline` and `graph_rag_knowledgement`
- Watch/backend developers: `app/operations_api` and `scripts/send_virtual_data.py`
- Dashboard developers: endpoints in `docs/WATCH_API.md`
- Frontend developers: `frontend`

## API groups

- Graph-RAG: `/ask`, `/law/...`, `/site-checklist-ui`, and existing compatibility routes
- Operations: `/api/watch/...`, `/api/equipment/...`, and `/api/dashboard/...`

Run everything together:

```powershell
python -m uvicorn main:app --app-dir app --host 0.0.0.0 --port 8000
```

Heart rate, attendance, equipment, and emergency data must remain in SQLite. Legal graph data must remain in Neo4j.
