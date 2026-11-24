from dataclasses import dataclass, field
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from app.utils.validators import URLValidationError, validate_public_url


MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class WebsiteFetchError(RuntimeError):
    """Raised when the target webpage cannot be retrieved or parsed as HTML."""


@dataclass
class ExtractedWebsite:
    requested_url: str
    final_url: str
    title: str = ""
    meta_description: str = ""
    site_name: str = ""
    headings: list[str] = field(default_factory=list)
    nav_items: list[str] = field(default_factory=list)
    structured_hints: list[str] = field(default_factory=list)
    body_text: str = ""

    def to_prompt_context(self) -> str:
        lines = [
            f"URL: {self.final_url}",
            f"Site Name: {self.site_name or 'N/A'}",
            f"Page Title: {self.title or 'N/A'}",
            f"Meta Description: {self.meta_description or 'N/A'}",
        ]
        if self.structured_hints:
            lines.append("Structured Metadata: " + " | ".join(self.structured_hints[:8]))
        if self.nav_items:
            lines.append("Navigation / Menu Topics: " + ", ".join(self.nav_items[:20]))
        if self.headings:
            lines.append("Key Headings:\n- " + "\n- ".join(self.headings[:25]))
        if self.body_text:
            lines.append(f"Extracted Page Content:\n{self.body_text}")
        return "\n\n".join(lines)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_jsonld_hints(soup: BeautifulSoup) -> list[str]:
    hints: list[str] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (tag.string or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            schema_type = node.get("@type")
            name = node.get("name")
            desc = node.get("description")
            parts = [str(x) for x in (schema_type, name, desc) if x]
            if parts:
                hints.append(_collapse_ws(" - ".join(parts))[:220])
    return hints


def parse_html_content(
    html: str,
    requested_url: str,
    final_url: str,
    max_chars: int = 12000,
) -> ExtractedWebsite:
    soup = BeautifulSoup(html, "lxml")
    structured_hints = _extract_jsonld_hints(soup)

    title = ""
    if soup.title and soup.title.string:
        title = _collapse_ws(soup.title.string)

    def _meta(attr_name: str, attr_val: str) -> str:
        tag = soup.find("meta", attrs={attr_name: re.compile(f"^{re.escape(attr_val)}$", re.I)})
        if tag and tag.get("content"):
            return _collapse_ws(str(tag["content"]))
        return ""

    meta_desc = _meta("name", "description") or _meta("property", "og:description")
    site_name = _meta("property", "og:site_name")
    if not title:
        title = _meta("property", "og:title")

    nav_items: list[str] = []
    seen_nav: set[str] = set()
    for nav in soup.find_all(["nav", "header"]):
        for anchor in nav.find_all("a"):
            label = _collapse_ws(anchor.get_text(" ", strip=True))
            if 2 < len(label) <= 45 and label.lower() not in seen_nav:
                seen_nav.add(label.lower())
                nav_items.append(label)

    # Strip boilerplate / non-visible DOM elements before reading body copy
    for noisy in soup(["script", "style", "noscript", "svg", "iframe", "canvas", "form"]):
        noisy.decompose()

    headings: list[str] = []
    seen_headings: set[str] = set()
    for h_tag in soup.find_all(["h1", "h2", "h3"]):
        text = _collapse_ws(h_tag.get_text(" ", strip=True))
        if 2 < len(text) <= 160 and text.lower() not in seen_headings:
            seen_headings.add(text.lower())
            headings.append(text)

    blocks: list[str] = []
    seen_blocks: set[str] = set()
    total_len = 0
    for elem in soup.find_all(["p", "li", "article", "section"]):
        # Avoid duplicating huge container text when child paragraphs exist
        if elem.name in ("article", "section") and elem.find(["p", "li"]):
            continue
        txt = _collapse_ws(elem.get_text(" ", strip=True))
        if len(txt) < 25:
            continue
        key = txt.lower()
        if key in seen_blocks:
            continue
        seen_blocks.add(key)
        blocks.append(txt)
        total_len += len(txt) + 1
        if total_len >= max_chars:
            break

    if not blocks and soup.body:
        fallback_text = _collapse_ws(soup.body.get_text(" ", strip=True))
        if fallback_text:
            blocks.append(fallback_text[:max_chars])

    body_text = "\n".join(blocks)[:max_chars]

    return ExtractedWebsite(
        requested_url=requested_url,
        final_url=final_url,
        title=title,
        meta_description=meta_desc,
        site_name=site_name,
        headings=headings,
        nav_items=nav_items,
        structured_hints=structured_hints,
        body_text=body_text,
    )


async def fetch_and_extract(
    url: str,
    timeout_seconds: float = 15.0,
    max_chars: int = 12000,
) -> ExtractedWebsite:
    current_url = validate_public_url(url)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=False,
        headers=headers,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with client.stream("GET", current_url) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise WebsiteFetchError("Redirect response missing Location header.")
                        next_url = urljoin(current_url, location)
                        # Re-validate every hop so open redirects cannot pivot to internal IPs
                        current_url = validate_public_url(next_url)
                        continue

                    if resp.status_code >= 400:
                        raise WebsiteFetchError(
                            f"Website returned HTTP {resp.status_code} for {current_url}."
                        )

                    content_type = (resp.headers.get("content-type") or "").lower()
                    if content_type and not any(
                        token in content_type
                        for token in ("text/html", "application/xhtml+xml", "text/plain")
                    ):
                        raise WebsiteFetchError(
                            f"Unsupported content type '{content_type}'. Expected an HTML page."
                        )

                    chunks: list[bytes] = []
                    downloaded = 0
                    async for chunk in resp.aiter_bytes():
                        chunks.append(chunk)
                        downloaded += len(chunk)
                        if downloaded >= MAX_RESPONSE_BYTES:
                            break

                    charset = resp.encoding or "utf-8"
                    raw_html = b"".join(chunks).decode(charset, errors="replace")
                    break
            except URLValidationError:
                raise
            except httpx.TimeoutException as exc:
                raise WebsiteFetchError(f"Timed out while connecting to {current_url}.") from exc
            except httpx.RequestError as exc:
                raise WebsiteFetchError(f"Failed to connect to {current_url}: {exc}") from exc
        else:
            raise WebsiteFetchError("Too many HTTP redirects while fetching website.")

    extracted = parse_html_content(
        html=raw_html,
        requested_url=url,
        final_url=current_url,
        max_chars=max_chars,
    )
    if not (extracted.title or extracted.meta_description or extracted.body_text):
        raise WebsiteFetchError(
            "Website returned empty or client-only shell content with no readable text."
        )
    return extracted
