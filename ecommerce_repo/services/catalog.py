from __future__ import annotations

import time


def fetch_catalog_page(page: int = 1) -> dict:
    if page < 1:
        raise ValueError("invalid page")
    # Simulated upstream call.
    time.sleep(0.01)
    return {"page": page, "items": [], "source": "catalog-provider-v1"}


def build_cache_key(tenant_id: str, page: int) -> str:
    return f"catalog:{tenant_id}:page:{page}"

