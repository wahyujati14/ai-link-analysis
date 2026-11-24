import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


async def fetch_competitor_hints(
    website_url: str,
    title: str,
    serper_api_key: str,
    timeout_seconds: float = 10.0,
) -> list[dict[str, str]]:
    """Query Serper search API for real-world competitor references when configured."""
    if not serper_api_key.strip():
        return []

    domain = (urlparse(website_url).hostname or "").removeprefix("www.")
    if not domain:
        return []

    brand_hint = title.split("|")[0].split("-")[0].strip()[:60] or domain
    query = f'"{domain}" OR "{brand_hint}" competitors alternatives'

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": serper_api_key.strip(),
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": 6},
            )
            if resp.status_code != 200:
                logger.warning("Serper search returned HTTP %s", resp.status_code)
                return []
            data = resp.json()
    except Exception as exc:
        logger.warning("Competitor search skipped due to error: %s", exc)
        return []

    results: list[dict[str, str]] = []
    for item in data.get("organic", [])[:6]:
        title_txt = str(item.get("title", "")).strip()
        snippet_txt = str(item.get("snippet", "")).strip()
        link_txt = str(item.get("link", "")).strip()
        if title_txt or snippet_txt:
            results.append(
                {
                    "title": title_txt,
                    "snippet": snippet_txt,
                    "link": link_txt,
                }
            )
    return results
