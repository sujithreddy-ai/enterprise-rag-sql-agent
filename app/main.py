import os
import re
import time
import sqlite3
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from pypdf import PdfReader
import chromadb
from google import genai
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

app = FastAPI(title="Enterprise Document RAG & Natural-Language SQL Agent")

def get_gemini_client():
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is missing in .env")
    return genai.Client(api_key=api_key)

def generate_with_retry(client: genai.Client, prompt: str, attempts: int = 4):
    model_name = (os.getenv("GEMINI_MODEL") or "gemini-3.8-flash").strip().strip('"').strip("'")
    last_err = None
    for idx in range(attempts):
        try:
            return client.models.generate_content(model=model_name, contents=prompt)
        except Exception as e:
            last_err = e
            msg = str(e)
            if ("503" in msg or "UNAVAILABLE" in msg or "429" in msg) and idx < attempts - 1:
                time.sleep(1.5 * (idx + 1))
                continue
            raise
    raise last_err

chroma_client = chromadb.PersistentClient(path=str(BASE_DIR / "chroma_store"))
collection = chroma_client.get_or_create_collection(name="enterprise_docs")

class QueryRequest(BaseModel):
    question: str

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50):
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ingest-doc")
async def ingest_doc(file: UploadFile = File(...)):
    reader = PdfReader(file.file)
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    chunks = chunk_text(full_text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No readable text found in PDF.")

    ids = [f"{file.filename}_chunk_{i}" for i in range(len(chunks))]
    collection.upsert(documents=chunks, ids=ids)
    return {"filename": file.filename, "chunks_indexed": len(chunks)}

@app.post("/ask-docs")
def ask_docs(req: QueryRequest):
    t0 = time.perf_counter()
    client = get_gemini_client()
    results = collection.query(query_texts=[req.question], n_results=3)
    docs = results["documents"][0] if results["documents"] else []
    ids = results["ids"][0] if results["ids"] else []

    context = "\n\n".join(f"[{cid}]: {doc}" for cid, doc in zip(ids, docs))
    prompt = (
        "Answer the user question strictly using the provided context. "
        "Cite source chunk IDs in brackets. If the answer is not in the context, say so.\n\n"
        f"Context:\n{context}\n\nQuestion: {req.question}"
    )
    try:
        response = generate_with_retry(client, prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {str(e)}")

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "answer": response.text,
        "sources": ids,
        "latency_ms": latency_ms
    }

@app.post("/ask-data")
def ask_data(req: QueryRequest):
    t0 = time.perf_counter()
    client = get_gemini_client()
    schema = "Table: sales_metrics(id, region, quarter, product_tier, revenue_inr, churned_accounts)"
    sql_prompt = (
        f"Convert this question into a single valid SQLite SELECT query using {schema}. "
        "Return ONLY raw SQL with no markdown formatting.\n"
        f"Question: {req.question}"
    )
    try:
        sql_resp = generate_with_retry(client, sql_prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {str(e)}")

    sql_query = (sql_resp.text or "").strip().removeprefix("```sql").removesuffix("```").strip()

    if not re.match(r"^\s*SELECT\b", sql_query, re.IGNORECASE) or re.search(
        r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|ATTACH)\b", sql_query, re.IGNORECASE
    ):
        raise HTTPException(status_code=400, detail=f"Unsafe SQL blocked: {sql_query}")

    db_path = BASE_DIR / "sample_data" / "sales_metrics.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(sql_query)
    columns = [desc[0] for desc in cur.description]
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    conn.close()

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "generated_sql": sql_query,
        "rows": rows[:20],
        "latency_ms": latency_ms
    }
