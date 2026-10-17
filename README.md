# SignalDesk

SignalDesk is a market-demand research assistant. Add reports, customer interviews, or market notes, then ask questions about recurring needs, demand signals, or underserved segments. Answers are grounded in retrieved passages and include source names and page numbers where available.

## Stack

- **FastAPI** serves the UI and API in one Python service.
- **Cloudflare Workers AI** hosts both the chat and embedding models. The recommended pair has a free daily inference allowance. Hugging Face Inference Providers and Ollama remain optional alternatives.
- **Supabase Postgres + pgvector** stores documents, text chunks, and embeddings in the cloud. Local development uses SQLite and exact cosine similarity.
- **Render** runs the Python web service. The included Blueprint config is set to its free instance.

## Run locally

Requires Python 3.11+ and a Cloudflare account with Workers AI access. The models run remotely; your computer only runs the SignalDesk web app.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

In Cloudflare Dashboard, open **Workers AI → Use REST API**, create a Workers AI API token, and copy your Account ID. Keep the token private. The Cloudflare guide describes the token setup and permissions: [REST API quick start](https://developers.cloudflare.com/workers-ai/get-started/rest-api/).

Set the following in `.env` (or add them if you already created that file):

```dotenv
LLM_PROVIDER=cloudflare
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_API_TOKEN=your_workers_ai_token
CLOUDFLARE_CHAT_MODEL=@cf/meta/llama-3.2-3b-instruct
CLOUDFLARE_EMBEDDING_MODEL=@cf/baai/bge-small-en-v1.5
```

The app loads `.env` automatically. Hugging Face and Ollama settings are not needed for this provider. Then:

```powershell
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The first run creates `data/signaldesk.sqlite3`. `/api/health` reports the selected provider and whether its credentials are configured. Embeddings and chat are sent to Cloudflare; the local SQLite database stores the source text and vectors.

To use hosted Hugging Face inference instead, set `LLM_PROVIDER=huggingface`, provide a fine-grained `HF_TOKEN` with **Make calls to Inference Providers** permission, and configure models with available providers. Hugging Face currently includes $0.10/month in credits for free accounts, subject to change; after that, requests return a payment-required error unless you add credits. See [HF pricing](https://huggingface.co/docs/inference-providers/pricing).

## Deploy on Render + Supabase

1. Create a Supabase project on its free plan. Open **SQL Editor**, paste [`supabase/schema.sql`](supabase/schema.sql), and run it. This enables pgvector and creates the document tables.
2. In Supabase **Project Settings → Database**, copy the connection string. Use the session pooler URL if direct IPv6 access is unavailable. Keep the database password private.
3. Push this project to a GitHub repository and create a Render **Blueprint** from it. Render reads `render.yaml` and creates the free web service.
4. In Render service **Environment**, set `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, and `DATABASE_URL`. The Blueprint selects Cloudflare Workers AI. Deploy.
5. Open the Render service URL. `/api/health` reports whether the Cloudflare credentials were detected and which storage mode is active.

Cloudflare Workers AI currently provides 10,000 free Neurons per day, resetting at 00:00 UTC; usage above that allowance fails on the Free plan. The selected Llama 3.2 3B and BGE Small models are listed in Cloudflare's current model catalog. See [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/), [Llama 3.2 3B](https://developers.cloudflare.com/workers-ai/models/@cf/meta/llama-3.2-3b-instruct/), and [BGE Small](https://developers.cloudflare.com/workers-ai/models/@cf/baai/bge-small-en-v1.5/). Render Free services sleep after 15 minutes idle and can take about a minute to wake up. Their local filesystem is ephemeral, so production deployment should set `DATABASE_URL` to Supabase; uploaded documents and vectors then survive restarts. Supabase free databases have a 500 MB database-size quota and can pause when inactive.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `cloudflare` | `cloudflare`, `huggingface`, or `ollama` |
| `CLOUDFLARE_ACCOUNT_ID` | empty | Account ID used for Workers AI REST calls |
| `CLOUDFLARE_API_TOKEN` | empty | Workers AI API token |
| `CLOUDFLARE_CHAT_MODEL` | `@cf/meta/llama-3.2-3b-instruct` | Cloudflare-hosted chat model |
| `CLOUDFLARE_EMBEDDING_MODEL` | `@cf/baai/bge-small-en-v1.5` | Cloudflare-hosted embedding model; returns 384 dimensions |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama API address |
| `OLLAMA_CHAT_MODEL` | `qwen2.5:3b` | Chat model pulled into Ollama |
| `OLLAMA_EMBEDDING_MODEL` | `all-minilm` | Local 384-dimensional embedding model |
| `HF_TOKEN` | empty | Hugging Face token for hosted inference mode |
| `HF_CHAT_MODEL` | `Qwen/Qwen2.5-7B-Instruct:fastest` | Chat model exposed by an HF Inference Provider |
| `HF_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Feature-extraction model; produces 384-dimensional vectors |
| `DATABASE_URL` | empty | Supabase/Postgres connection string; empty uses local SQLite |
| `MAX_UPLOAD_MB` | `15` | Per-file upload limit |

The Supabase vector column is configured for 384 dimensions to match the default embedding models. If you change embedding models, keep the model output dimension and `extensions.vector(384)` in [`supabase/schema.sql`](supabase/schema.sql) in sync. Re-upload documents after switching embedding models so their stored vectors and question vectors use the same model.

## Supported files

PDF (text-based), DOCX, TXT, Markdown, and CSV. Scanned PDFs need OCR before upload. One file can produce at most 250 chunks. Answers are generated only from the top five retrieved excerpts and explicitly say when the sources do not support a claim.

## API

- `GET /api/health` — readiness and storage mode.
- `GET /api/stats` — document/chunk counts and configured model.
- `GET /api/documents` — list uploaded sources.
- `POST /api/documents` — upload a multipart `file`.
- `DELETE /api/documents/{id}` — remove a source and its chunks.
- `POST /api/chat` — JSON body: `{"question":"..."}`.
