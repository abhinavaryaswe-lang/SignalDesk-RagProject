import json
import sqlite3
from datetime import datetime, timezone

from .config import DATA_DIR, DB_PATH, DATABASE_URL


def _sqlite():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    if DATABASE_URL:
        with _pg() as conn:
            with conn.cursor() as cur:
                cur.execute("select to_regclass('public.documents') as table_name")
                if cur.fetchone()["table_name"] is None:
                    raise RuntimeError("Supabase schema is missing. Run supabase/schema.sql in the SQL Editor.")
        return
    with _sqlite() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, file_type TEXT NOT NULL,
          size_bytes INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS document_chunks (
          id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          content TEXT NOT NULL, page INTEGER, embedding TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx ON document_chunks(document_id);
        """)


def _pg():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(DATABASE_URL, autocommit=False, prepare_threshold=None, row_factory=dict_row)


def add_document(doc_id, name, file_type, size_bytes, chunks):
    created_at = datetime.now(timezone.utc).isoformat()
    if DATABASE_URL:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO documents(id,name,file_type,size_bytes) VALUES (%s,%s,%s,%s)",
                        (doc_id, name, file_type, size_bytes))
            cur.executemany("INSERT INTO document_chunks(document_id,content,page,embedding) VALUES (%s,%s,%s,%s::extensions.vector)",
                            [(doc_id, text, page, "[" + ",".join(map(str, vector)) + "]") for text, page, vector in chunks])
        return created_at
    with _sqlite() as conn:
        conn.execute("INSERT INTO documents VALUES (?,?,?,?,?)", (doc_id, name, file_type, size_bytes, created_at))
        conn.executemany("INSERT INTO document_chunks(document_id,content,page,embedding) VALUES (?,?,?,?)",
                         [(doc_id, text, page, json.dumps(vector)) for text, page, vector in chunks])
    return created_at


def list_documents():
    if DATABASE_URL:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute("SELECT d.id,d.name,d.file_type,d.size_bytes,d.created_at,count(c.id) AS chunks FROM documents d LEFT JOIN document_chunks c ON c.document_id=d.id GROUP BY d.id ORDER BY d.created_at DESC")
            return [dict(r) for r in cur.fetchall()]
    with _sqlite() as conn:
        rows = conn.execute("SELECT d.*,count(c.id) AS chunks FROM documents d LEFT JOIN document_chunks c ON c.document_id=d.id GROUP BY d.id ORDER BY d.created_at DESC").fetchall()
        return [dict(r) for r in rows]


def delete_document(doc_id):
    if DATABASE_URL:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE id=%s", (doc_id,))
            return cur.rowcount > 0
    with _sqlite() as conn:
        cur = conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        return cur.rowcount > 0


def search_chunks(query_vector, limit):
    if DATABASE_URL:
        vector = "[" + ",".join(map(str, query_vector)) + "]"
        with _pg() as conn, conn.cursor() as cur:
            cur.execute("""SELECT c.content,c.page,d.name,1-(c.embedding <=> %s::extensions.vector) AS score
                           FROM document_chunks c JOIN documents d ON d.id=c.document_id
                           ORDER BY c.embedding <=> %s::extensions.vector LIMIT %s""", (vector, vector, limit))
            return [dict(zip(("content", "page", "name", "score"), r)) for r in cur.fetchall()]
    import math
    with _sqlite() as conn:
        rows = conn.execute("SELECT c.content,c.page,d.name,c.embedding FROM document_chunks c JOIN documents d ON d.id=c.document_id").fetchall()
    qnorm = math.sqrt(sum(x*x for x in query_vector)) or 1
    scored = []
    for row in rows:
        vector = json.loads(row["embedding"])
        denom = qnorm * (math.sqrt(sum(x*x for x in vector)) or 1)
        score = sum(a*b for a, b in zip(query_vector, vector)) / denom
        scored.append({"content": row["content"], "page": row["page"], "name": row["name"], "score": score})
    return sorted(scored, key=lambda x: x["score"], reverse=True)[:limit]


def document_count():
    if DATABASE_URL:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM documents")
            return cur.fetchone()["count"]
    with _sqlite() as conn:
        return conn.execute("SELECT count(*) FROM documents").fetchone()[0]
