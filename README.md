# Enterprise Document RAG & Natural-Language SQL Agent

FastAPI backend combining grounded PDF Retrieval-Augmented Generation (ChromaDB + Google GenAI SDK) with a read-only Text-to-SQL analytics agent over structured SQLite business metrics.

## Endpoints
- `GET /health` — Service health check
- `POST /ingest-doc` — PDF text extraction, overlapping chunking, and ChromaDB vector indexing
- `POST /ask-docs` — Top-k semantic retrieval with source chunk citations and latency telemetry (`latency_ms`)
- `POST /ask-data` — Natural-language to read-only SQLite `SELECT` agent with regex write-guardrails

## Quickstart
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed_db.py
uvicorn app.main:app --reload
```
