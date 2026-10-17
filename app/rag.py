import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from huggingface_hub import InferenceClient

from .config import CHAT_MODEL, CF_ACCOUNT_ID, CF_API_TOKEN, CF_CHAT_MODEL, CF_EMBEDDING_MODEL, EMBEDDING_MODEL, HF_TOKEN, LLM_PROVIDER, OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, OLLAMA_EMBEDDING_MODEL, TOP_K
from .database import search_chunks


def _client():
    if not HF_TOKEN:
        raise RuntimeError("Add your Hugging Face access token as HF_TOKEN in the environment settings.")
    return InferenceClient(token=HF_TOKEN, timeout=90)


def _ollama_request(path, payload=None, timeout=180):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(f"{OLLAMA_BASE_URL}{path}", data=data,
                      headers={"Content-Type": "application/json"} if data else {},
                      method="POST" if data else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {details[:300]}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Cannot reach Ollama at " + OLLAMA_BASE_URL + ". Start the Ollama app and make sure the models are installed.") from exc


def _cloudflare_request(model, payload, timeout=120):
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        raise RuntimeError("Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN to use Cloudflare Workers AI.")
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{model}"
    request = Request(url, data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"},
                      method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cloudflare Workers AI returned HTTP {exc.code}: {details[:400]}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Could not reach the Cloudflare Workers AI API.") from exc
    if not body.get("success", True):
        raise RuntimeError(f"Cloudflare Workers AI error: {str(body.get('errors', body))[:400]}")
    return body.get("result", {})


def provider_status():
    if LLM_PROVIDER == "cloudflare":
        ready = bool(CF_ACCOUNT_ID and CF_API_TOKEN)
        return {"ready": ready, "detail": "Cloudflare credentials ready" if ready else "Add Cloudflare credentials"}
    if LLM_PROVIDER != "ollama":
        return {"ready": bool(HF_TOKEN), "detail": "HF_TOKEN is set" if HF_TOKEN else "Add HF_TOKEN"}
    try:
        installed = {item.get("name") for item in _ollama_request("/api/tags").get("models", [])}
    except Exception:
        return {"ready": False, "detail": "Start Ollama"}
    missing = [
        name for name in (OLLAMA_CHAT_MODEL, OLLAMA_EMBEDDING_MODEL)
        if name not in installed and (":" in name or f"{name}:latest" not in installed)
    ]
    if missing:
        return {"ready": False, "detail": "Pull Ollama models"}
    return {"ready": True, "detail": "Local models ready"}


def embed_texts(texts):
    if LLM_PROVIDER == "cloudflare":
        vectors = []
        for start in range(0, len(texts), 8):
            result = _cloudflare_request(CF_EMBEDDING_MODEL, {"text": texts[start:start + 8]})
            vectors.extend(result.get("data", []))
        if len(vectors) != len(texts):
            raise RuntimeError("Cloudflare returned an unexpected embedding response.")
        return vectors
    if LLM_PROVIDER == "ollama":
        vectors = []
        for start in range(0, len(texts), 8):
            result = _ollama_request("/api/embed", {"model": OLLAMA_EMBEDDING_MODEL, "input": texts[start:start + 8]})
            vectors.extend(result["embeddings"])
        return vectors
    client = _client()
    vectors = []
    # Small batches avoid provider payload limits and keep uploads responsive.
    for start in range(0, len(texts), 8):
        result = client.feature_extraction(texts[start:start + 8], model=EMBEDDING_MODEL)
        if hasattr(result, "tolist"):
            result = result.tolist()
        vectors.extend(result)
    return vectors


def answer_question(question):
    client = _client() if LLM_PROVIDER == "huggingface" else None
    query_vector = embed_texts([question])[0]
    sources = search_chunks(query_vector, TOP_K)
    if not sources:
        return {"answer": "I don't have any source documents yet. Upload market reports, research, or customer feedback and ask again.", "sources": []}
    context = "\n\n".join(
        f"[Source {i}: {s['name']}" + (f", page {s['page']}" if s.get("page") else "") + f"]\n{s['content']}"
        for i, s in enumerate(sources, 1)
    )
    prompt = f"""You are SignalDesk, a careful market-demand research analyst. Answer the question using only the provided source excerpts. If the excerpts do not support a claim, say what is missing. Distinguish evidence from interpretation, and never invent market size, dates, or statistics. Cite factual claims inline with [1], [2], matching the source labels. Keep the answer clear and useful.

SOURCE EXCERPTS:
{context}

QUESTION: {question}"""
    if LLM_PROVIDER == "cloudflare":
        result = _cloudflare_request(CF_CHAT_MODEL, {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 700,
            "temperature": 0.2,
        })
        text = result.get("response") or "I couldn't form an answer from those excerpts."
    elif LLM_PROVIDER == "ollama":
        response = _ollama_request("/api/chat", {
            "model": OLLAMA_CHAT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"num_predict": 700, "temperature": 0.2},
        })
        text = response.get("message", {}).get("content") or "I couldn't form an answer from those excerpts."
    else:
        response = client.chat_completion(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
            temperature=0.2,
        )
        text = response.choices[0].message.content or "I couldn't form an answer from those excerpts."
    return {"answer": text, "sources": [
        {"index": i, "name": s["name"], "page": s.get("page"), "score": round(float(s["score"]), 3), "excerpt": s["content"][:300]}
        for i, s in enumerate(sources, 1)
    ]}
