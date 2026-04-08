#!/usr/bin/env python3
"""Fill PRODUCT_TEXT_EMBEDDING.embedding using a sentence-transformers model.

Reads rows from PRODUCT_TEXT_EMBEDDING and writes vector(384) embeddings
using pgvector's native cast syntax.

Usage:
  python3 scripts/db/fill_product_embeddings.py
  python3 scripts/db/fill_product_embeddings.py --limit 5
  python3 scripts/db/fill_product_embeddings.py --force
  python3 scripts/db/fill_product_embeddings.py --device cpu
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable

import psycopg2
import psycopg2.extras
from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EXPECTED_DIM = 384


def load_env_file() -> None:
    """Load .env values when env vars are not set."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        user=os.environ.get("PG_USER", "shoppinkki"),
        password=os.environ.get("PG_PASSWORD", "shoppinkki"),
        dbname=os.environ.get("PG_DATABASE", "shoppinkki"),
    )


def build_select_query(force: bool, limit: int | None) -> tuple[str, tuple]:
    where_clause = "" if force else "WHERE embedding IS NULL"
    limit_clause = " LIMIT %s" if limit is not None else ""
    params: tuple = (limit,) if limit is not None else ()
    query = (
        "SELECT id, text FROM PRODUCT_TEXT_EMBEDDING "
        f"{where_clause} "
        "ORDER BY id"
        f"{limit_clause}"
    )
    return query, params


def vector_to_string(values: Iterable[float]) -> str:
    # pgvector expects a string like: "[0.1, 0.2, ...]"
    return "[" + ", ".join(f"{value:.8f}" for value in values) + "]"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fill PRODUCT_TEXT_EMBEDDING.embedding with sentence embeddings."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="sentence-transformers model name")
    parser.add_argument("--batch-size", type=int, default=16, help="embedding batch size")
    parser.add_argument("--limit", type=int, default=None, help="max number of rows to process")
    parser.add_argument("--force", action="store_true", help="rebuild embeddings for all rows")
    parser.add_argument("--device", default=None, help="device override, e.g. cpu")
    args = parser.parse_args()

    load_env_file()

    print(f"[1/4] Loading model: {args.model}")
    model_kwargs = {"device": args.device} if args.device else {}
    model = SentenceTransformer(args.model, **model_kwargs)

    dim = model.get_sentence_embedding_dimension()
    if dim != EXPECTED_DIM:
        raise ValueError(
            f"Model dimension {dim} does not match schema vector({EXPECTED_DIM})."
        )

    print("[2/4] Connecting to PostgreSQL")
    conn = get_connection()
    select_cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query, params = build_select_query(force=args.force, limit=args.limit)
    select_cursor.execute(query, params)
    rows = select_cursor.fetchall()

    if not rows:
        print("No rows to update.")
        select_cursor.close()
        conn.close()
        return 0

    ids = [row["id"] for row in rows]
    texts = [row["text"] for row in rows]
    print(f"[3/4] Encoding {len(rows)} rows")

    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    print("[4/4] Writing embeddings to PostgreSQL")
    update_cursor = conn.cursor()
    update_sql = """
        UPDATE PRODUCT_TEXT_EMBEDDING
        SET embedding = %s::vector,
            model_name = %s
        WHERE id = %s
    """
    payload = [
        (vector_to_string(embedding.tolist()), args.model, row_id)
        for row_id, embedding in zip(ids, embeddings, strict=True)
    ]
    update_cursor.executemany(update_sql, payload)
    conn.commit()

    print(f"Updated {update_cursor.rowcount} rows.")
    update_cursor.close()
    select_cursor.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
