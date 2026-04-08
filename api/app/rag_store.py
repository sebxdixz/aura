from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_rag_schema(db: Session, *, embedding_dim: int = 1536) -> None:
    dim = max(8, int(embedding_dim))
    db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    db.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS code_chunks (
                id BIGSERIAL PRIMARY KEY,
                repo_name VARCHAR(120) NOT NULL,
                file_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding vector({dim}) NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (repo_name, file_path, chunk_index)
            )
            """
        )
    )
    db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_code_chunks_repo
            ON code_chunks (repo_name)
            """
        )
    )
    db.commit()

    # ivfflat can fail if extension/index params are not available yet.
    try:
        db.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding
                ON code_chunks USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )
        )
        db.commit()
    except Exception:
        db.rollback()


def clear_repo_chunks(db: Session, *, repo_name: str) -> int:
    result = db.execute(
        text("DELETE FROM code_chunks WHERE repo_name = :repo_name"),
        {"repo_name": repo_name},
    )
    db.commit()
    return int(result.rowcount or 0)


def upsert_code_chunk(
    db: Session,
    *,
    repo_name: str,
    file_path: str,
    chunk_index: int,
    content: str,
    embedding_literal: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO code_chunks (
                repo_name, file_path, chunk_index, content, embedding, metadata
            ) VALUES (
                :repo_name, :file_path, :chunk_index, :content,
                CAST(:embedding_literal AS vector),
                CAST(:metadata AS jsonb)
            )
            ON CONFLICT (repo_name, file_path, chunk_index) DO UPDATE
            SET content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata
            """
        ),
        {
            "repo_name": repo_name,
            "file_path": file_path,
            "chunk_index": chunk_index,
            "content": content,
            "embedding_literal": embedding_literal,
            "metadata": json.dumps(metadata or {}),
        },
    )


def commit_chunks(db: Session) -> None:
    db.commit()


def search_code_chunks(
    db: Session,
    *,
    repo_name: str,
    embedding_literal: str,
    top_k: int = 4,
) -> list[dict[str, Any]]:
    safe_k = max(1, min(int(top_k), 20))
    rows = db.execute(
        text(
            """
            SELECT
                file_path,
                chunk_index,
                content,
                metadata,
                1 - (embedding <=> CAST(:embedding_literal AS vector)) AS similarity
            FROM code_chunks
            WHERE repo_name = :repo_name
            ORDER BY embedding <=> CAST(:embedding_literal AS vector)
            LIMIT :top_k
            """
        ),
        {
            "repo_name": repo_name,
            "embedding_literal": embedding_literal,
            "top_k": safe_k,
        },
    ).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        payload = row.metadata if isinstance(row.metadata, dict) else {}
        results.append(
            {
                "file_path": row.file_path,
                "chunk_index": row.chunk_index,
                "content": row.content,
                "metadata": payload,
                "similarity": float(row.similarity or 0.0),
            }
        )
    return results


def count_repo_chunks(db: Session, *, repo_name: str) -> int:
    row = db.execute(
        text("SELECT COUNT(*) AS total FROM code_chunks WHERE repo_name = :repo_name"),
        {"repo_name": repo_name},
    ).fetchone()
    return int(row.total if row else 0)
