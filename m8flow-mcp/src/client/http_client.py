"""Shared HTTP client with connection pooling for m8flow API"""

import httpx

from src.config import settings

# Global shared client instance
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared async HTTP client with connection pooling.

    Benefits:
    - Reuses connections (faster)
    - Connection pooling (handles multiple concurrent requests)
    - Single instance (memory efficient)

    Returns:
        Shared httpx.AsyncClient instance
    """
    global _http_client

    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=settings.m8flow_api_timeout,
            headers={
                "User-Agent": "m8flow-mcp/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
            ),
        )

    return _http_client


async def shutdown_http_client() -> None:
    """Shutdown the shared HTTP client (cleanup on exit)"""
    global _http_client

    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
