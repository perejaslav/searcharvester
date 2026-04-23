"""Small synchronous client for the Searcharvester HTTP API.

This module is intentionally a client for the adapter API, not a second
SearXNG scraper implementation. The server-side Tavily response models live in
`models.py`.
"""
from __future__ import annotations

from typing import Any

import httpx

from models import TavilyResponse, TavilyResult


class TavilyClient:
    def __init__(
        self,
        api_key: str = "",
        base_url: str | None = None,
        searxng_url: str | None = None,
    ):
        self.api_key = api_key  # accepted for Tavily SDK compatibility
        # Backward-compatible alias: older local scripts passed searxng_url.
        # The value now points to the Searcharvester adapter base URL.
        self.base_url = (base_url or searxng_url or "http://localhost:8000").rstrip("/")

    def search(
        self,
        query: str,
        max_results: int = 10,
        include_raw_content: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "include_raw_content": include_raw_content,
        }
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        with httpx.Client(timeout=60) as client:
            response = client.post(f"{self.base_url}/search", json=payload)
            response.raise_for_status()
            return response.json()

    def extract(self, url: str, size: str = "m") -> dict[str, Any]:
        with httpx.Client(timeout=60) as client:
            response = client.post(f"{self.base_url}/extract", json={"url": url, "size": size})
            response.raise_for_status()
            return response.json()
