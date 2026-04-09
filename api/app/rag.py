from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from sqlalchemy.orm import Session

from .integrations.llm import get_openai_client
from .observability import log_event
from .rag_store import (
    clear_repo_chunks,
    commit_chunks,
    count_repo_chunks,
    ensure_rag_schema,
    search_code_chunks,
    upsert_code_chunk,
)

_TEXT_FILE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".java",
    ".rb",
    ".php",
    ".cs",
    ".rs",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".sql",
    ".cfg",
    ".ini",
    ".sh",
    ".env",
}

_SKIP_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    ".next",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
}

_RAG_SCHEMA_READY = False


def rag_repo_name() -> str:
    return os.getenv("RAG_REPO_NAME", "ecommerce")


def rag_default_tenant_id() -> str:
    return os.getenv("RAG_DEFAULT_TENANT_ID", "default")


def rag_embedding_dim() -> int:
    value = os.getenv("RAG_EMBEDDING_DIM", "1536")
    try:
        return max(128, int(value))
    except ValueError:
        return 1536


def rag_top_k() -> int:
    value = os.getenv("RAG_TOP_K", "4")
    try:
        return max(1, min(20, int(value)))
    except ValueError:
        return 4


def rag_path() -> str:
    return os.getenv("ECOMMERCE_CODEBASE_PATH", "/workspace/ecommerce_repo")


def ensure_vector_ready(db: Session) -> None:
    global _RAG_SCHEMA_READY
    if _RAG_SCHEMA_READY:
        return
    ensure_rag_schema(db, embedding_dim=rag_embedding_dim())
    _RAG_SCHEMA_READY = True


def auto_index_enabled() -> bool:
    return os.getenv("RAG_AUTO_INDEX", "true").strip().lower() in {"1", "true", "yes", "on"}


def rag_status(db: Session, *, tenant_id: str | None = None) -> dict[str, Any]:
    ensure_vector_ready(db)
    tenant = (tenant_id or rag_default_tenant_id()).strip() or rag_default_tenant_id()
    repo = rag_repo_name()
    path = rag_path()
    chunks = count_repo_chunks(db, tenant_id=tenant, repo_name=repo)
    return {
        "tenant_id": tenant,
        "repo_name": repo,
        "codebase_path": path,
        "path_exists": Path(path).exists(),
        "indexed_chunks": chunks,
        "embedding_dim": rag_embedding_dim(),
    }


def reindex_codebase(db: Session, *, tenant_id: str | None = None, repo_name: str | None = None) -> dict[str, Any]:
    ensure_vector_ready(db)

    tenant = (tenant_id or rag_default_tenant_id()).strip() or rag_default_tenant_id()
    repo = (repo_name or rag_repo_name()).strip() or rag_repo_name()
    root = Path(rag_path())
    if not root.exists() or not root.is_dir():
        return {
            "repo_name": repo,
            "tenant_id": tenant,
            "codebase_path": str(root),
            "indexed_files": 0,
            "indexed_chunks": 0,
            "cleared_chunks": 0,
            "skipped": True,
            "reason": "codebase path not found",
        }

    max_files = _safe_int("RAG_MAX_FILES", 500, minimum=1, maximum=5000)
    max_chunks_per_file = _safe_int("RAG_MAX_CHUNKS_PER_FILE", 50, minimum=1, maximum=500)
    chunk_size = _safe_int("RAG_CHUNK_SIZE", 1200, minimum=200, maximum=8000)
    overlap = _safe_int("RAG_CHUNK_OVERLAP", 200, minimum=0, maximum=2000)

    files = list(_iter_source_files(root, max_files=max_files))
    cleared = clear_repo_chunks(db, tenant_id=tenant, repo_name=repo)
    indexed_files = 0
    indexed_chunks = 0

    for file_path in files:
        raw_text = _safe_read_text(file_path)
        if not raw_text:
            continue
        chunks = _chunk_text(raw_text, chunk_size=chunk_size, overlap=overlap)
        chunk_count = 0
        for idx, chunk in enumerate(chunks):
            if chunk_count >= max_chunks_per_file:
                break
            cleaned = " ".join(chunk.split())
            if not cleaned:
                continue
            embedding = _embed_text(cleaned)
            upsert_code_chunk(
                db,
                tenant_id=tenant,
                repo_name=repo,
                file_path=str(file_path.relative_to(root)).replace("\\", "/"),
                chunk_index=idx,
                content=chunk[:2000],
                embedding_literal=_embedding_literal(embedding),
                metadata={
                    "source": "ecommerce_codebase",
                    "chunk_size": len(chunk),
                },
            )
            chunk_count += 1
            indexed_chunks += 1
        if chunk_count > 0:
            indexed_files += 1

    commit_chunks(db)
    log_event(
        "rag_index_completed",
        tenant_id=tenant,
        repo_name=repo,
        indexed_files=indexed_files,
        indexed_chunks=indexed_chunks,
        cleared_chunks=cleared,
    )
    return {
        "repo_name": repo,
        "tenant_id": tenant,
        "codebase_path": str(root),
        "indexed_files": indexed_files,
        "indexed_chunks": indexed_chunks,
        "cleared_chunks": cleared,
        "skipped": False,
    }


def retrieve_code_context(
    db: Session,
    *,
    tenant_id: str | None = None,
    query_text: str,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    ensure_vector_ready(db)
    tenant = (tenant_id or rag_default_tenant_id()).strip() or rag_default_tenant_id()
    query = " ".join((query_text or "").split())
    if not query:
        return []

    embedding = _embed_text(query)
    results = search_code_chunks(
        db,
        tenant_id=tenant,
        repo_name=rag_repo_name(),
        embedding_literal=_embedding_literal(embedding),
        top_k=top_k or rag_top_k(),
    )
    contexts: list[dict[str, Any]] = []
    for row in results:
        contexts.append(
            {
                "file_path": row["file_path"],
                "snippet": _shorten(str(row["content"]), limit=320),
                "similarity": float(row.get("similarity", 0.0)),
            }
        )
    if contexts:
        log_event("rag_retrieval_completed", tenant_id=tenant, matched_chunks=len(contexts))
    return contexts


def index_github_repository(
    db: Session,
    *,
    tenant_id: str,
    repo_url: str,
    branch: str | None = None,
) -> dict[str, Any]:
    ensure_vector_ready(db)
    tenant = tenant_id.strip()
    if not tenant:
        raise ValueError("tenant_id is required")

    owner, repo = _parse_github_repo(repo_url)
    default_branch = branch.strip() if branch else _github_default_branch(owner, repo)
    source_repo = f"{owner}/{repo}"
    repo_name = rag_repo_name()

    max_files = _safe_int("RAG_MAX_FILES", 500, minimum=1, maximum=5000)
    max_chunks_per_file = _safe_int("RAG_MAX_CHUNKS_PER_FILE", 50, minimum=1, maximum=500)
    chunk_size = _safe_int("RAG_CHUNK_SIZE", 1200, minimum=200, maximum=8000)
    overlap = _safe_int("RAG_CHUNK_OVERLAP", 200, minimum=0, maximum=2000)
    max_file_bytes = _safe_int("RAG_MAX_FILE_BYTES", 200_000, minimum=1_000, maximum=5_000_000)

    tree = _github_tree(owner, repo, default_branch)
    candidate_paths = [item["path"] for item in tree if _is_supported_path(item["path"])]
    selected_paths = candidate_paths[:max_files]

    cleared = clear_repo_chunks(db, tenant_id=tenant, repo_name=repo_name)
    indexed_files = 0
    indexed_chunks = 0

    for path in selected_paths:
        content = _github_raw_text(owner, repo, default_branch, path, max_bytes=max_file_bytes)
        if not content:
            continue
        chunks = _chunk_text(content, chunk_size=chunk_size, overlap=overlap)
        chunk_count = 0
        for idx, chunk in enumerate(chunks):
            if chunk_count >= max_chunks_per_file:
                break
            cleaned = " ".join(chunk.split())
            if not cleaned:
                continue
            embedding = _embed_text(cleaned)
            upsert_code_chunk(
                db,
                tenant_id=tenant,
                repo_name=repo_name,
                file_path=path,
                chunk_index=idx,
                content=chunk[:2000],
                embedding_literal=_embedding_literal(embedding),
                metadata={
                    "source": "github",
                    "source_repo": source_repo,
                    "repo_url": repo_url,
                    "branch": default_branch,
                    "chunk_size": len(chunk),
                },
            )
            chunk_count += 1
            indexed_chunks += 1
        if chunk_count > 0:
            indexed_files += 1

    commit_chunks(db)
    log_event(
        "rag_github_index_completed",
        tenant_id=tenant,
        repo_name=source_repo,
        branch=default_branch,
        indexed_files=indexed_files,
        indexed_chunks=indexed_chunks,
        cleared_chunks=cleared,
    )
    return {
        "tenant_id": tenant,
        "repo_name": source_repo,
        "storage_repo_name": repo_name,
        "branch": default_branch,
        "indexed_files": indexed_files,
        "indexed_chunks": indexed_chunks,
        "cleared_chunks": cleared,
        "skipped": False,
    }


def _parse_github_repo(repo_url: str) -> tuple[str, str]:
    parsed = urllib_parse.urlparse(repo_url.strip())
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ValueError("Only github.com repositories are supported")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("Invalid GitHub repository URL")
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    return owner, repo


def _github_default_branch(owner: str, repo: str) -> str:
    payload = _github_json(f"https://api.github.com/repos/{owner}/{repo}")
    branch = str(payload.get("default_branch", "")).strip()
    if not branch:
        raise ValueError("Unable to resolve default branch from GitHub")
    return branch


def _github_tree(owner: str, repo: str, ref: str) -> list[dict[str, Any]]:
    safe_ref = urllib_parse.quote(ref, safe="")
    payload = _github_json(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{safe_ref}?recursive=1")
    tree = payload.get("tree", [])
    if not isinstance(tree, list):
        return []
    blobs: list[dict[str, Any]] = []
    for item in tree:
        if isinstance(item, dict) and item.get("type") == "blob" and isinstance(item.get("path"), str):
            blobs.append(item)
    return blobs


def _github_raw_text(owner: str, repo: str, ref: str, file_path: str, *, max_bytes: int) -> str:
    quoted_path = urllib_parse.quote(file_path, safe="/-_.~")
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{quoted_path}"
    data = _http_get_bytes(url)
    if not data or len(data) > max_bytes:
        return ""
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding, errors="ignore")
        except Exception:
            continue
    return ""


def _github_json(url: str) -> dict[str, Any]:
    data = _http_get_bytes(url)
    if not data:
        raise ValueError(f"GitHub request failed: {url}")
    payload = json.loads(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected GitHub response for {url}")
    return payload


def _http_get_bytes(url: str) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "aura-rag-ingestor",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib_request.Request(url=url, headers=headers, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=20) as response:  # noqa: S310
            return response.read()
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ValueError(f"GitHub HTTP {exc.code} for {url}: {detail[:200]}") from exc
    except urllib_error.URLError as exc:
        raise ValueError(f"GitHub connection failed for {url}: {exc.reason}") from exc


def _is_supported_path(path: str) -> bool:
    clean = path.strip()
    if not clean:
        return False
    parts = clean.split("/")
    if any(part in _SKIP_DIRS for part in parts):
        return False
    suffix = Path(clean).suffix.lower()
    return suffix in _TEXT_FILE_EXTENSIONS


def _iter_source_files(root: Path, *, max_files: int) -> list[Path]:
    collected: list[Path] = []
    for path in root.rglob("*"):
        if len(collected) >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _TEXT_FILE_EXTENSIONS:
            continue
        collected.append(path)
    return collected


def _safe_read_text(path: Path) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=encoding, errors="ignore")
        except Exception:
            continue
    return ""


def _chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    compact = text.replace("\r\n", "\n").strip()
    if not compact:
        return []
    if len(compact) <= chunk_size:
        return [compact]
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for start in range(0, len(compact), step):
        end = start + chunk_size
        chunk = compact[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(compact):
            break
    return chunks


def _embed_text(text: str) -> list[float]:
    client = get_openai_client()
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    if client is not None and os.getenv("MOCK_MODE", "true").lower() == "false":
        try:
            response = client.embeddings.create(model=model, input=text)
            vector = response.data[0].embedding
            if isinstance(vector, list) and vector:
                return _normalize_dimension([float(v) for v in vector], rag_embedding_dim())
        except Exception:
            pass
    return _deterministic_embedding(text, dim=rag_embedding_dim())


def _deterministic_embedding(text: str, *, dim: int) -> list[float]:
    vector = [0.0] * dim
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + (digest[5] / 255.0)
        vector[idx] += sign * weight
    return _l2_normalize(vector)


def _normalize_dimension(values: list[float], dim: int) -> list[float]:
    if len(values) == dim:
        return _l2_normalize(values)
    if len(values) > dim:
        return _l2_normalize(values[:dim])
    padded = values + [0.0] * (dim - len(values))
    return _l2_normalize(padded)


def _l2_normalize(values: list[float]) -> list[float]:
    norm = sum(v * v for v in values) ** 0.5
    if norm == 0:
        return values
    return [v / norm for v in values]


def _embedding_literal(values: list[float]) -> str:
    compact = ",".join(f"{v:.8f}" for v in values)
    return f"[{compact}]"


def _shorten(text: str, *, limit: int = 320) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _safe_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        parsed = int(raw)
    except ValueError:
        parsed = default
    return max(minimum, min(parsed, maximum))
