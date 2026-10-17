import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
DB_PATH = DATA_DIR / "signaldesk.sqlite3"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "cloudflare").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:3b")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "all-minilm")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
CF_CHAT_MODEL = os.getenv("CLOUDFLARE_CHAT_MODEL", "@cf/meta/llama-3.2-3b-instruct")
CF_EMBEDDING_MODEL = os.getenv("CLOUDFLARE_EMBEDDING_MODEL", "@cf/baai/bge-small-en-v1.5")
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
HF_CHAT_MODEL = os.getenv("HF_CHAT_MODEL", "Qwen/Qwen2.5-7B-Instruct:fastest")
HF_EMBEDDING_MODEL = os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
if LLM_PROVIDER == "ollama":
    CHAT_MODEL, EMBEDDING_MODEL = OLLAMA_CHAT_MODEL, OLLAMA_EMBEDDING_MODEL
elif LLM_PROVIDER == "cloudflare":
    CHAT_MODEL, EMBEDDING_MODEL = CF_CHAT_MODEL, CF_EMBEDDING_MODEL
else:
    CHAT_MODEL, EMBEDDING_MODEL = HF_CHAT_MODEL, HF_EMBEDDING_MODEL
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "15"))
CHUNK_SIZE = 900
CHUNK_OVERLAP = 140
TOP_K = 5
