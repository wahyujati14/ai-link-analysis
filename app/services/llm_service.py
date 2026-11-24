import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = {
    "google": "Google",
    "google search": "Google",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "linkedin": "LinkedIn",
    "x": "X",
    "twitter": "X",
    "x (twitter)": "X",
}

SYSTEM_PROMPT = """You are a senior digital marketing, SEO, and competitive intelligence analyst.
Analyze the supplied website content and produce a single valid JSON object matching the exact schema below.

Rules:
1. Base brand details, services, SEO recommendations, and target audiences strictly on the extracted website content.
2. If the website has fewer than 5 explicit services, include inferred complementary services and set "is_inferred": true on those items (set "is_inferred": false for services directly present on the page).
3. Identify at least 3 relevant competitors. If "Live Search Competitor Hints" are provided and verify a competitor, set "source": "web_research"; otherwise set "source": "ai_suggested".
4. Generate exactly 5 target search queries across relevant platforms from this allowed list only: ["Google", "Facebook", "Instagram", "LinkedIn", "X"]. Never invent search volume numbers or rankings.
5. Output raw JSON only without markdown fences or extra commentary.

Required JSON structure:
{
  "brand": {
    "name": "string",
    "category": "string",
    "summary": "string"
  },
  "analysis": {
    "competitor_analysis": {
      "brand_overview": "string",
      "main_products_and_services": ["string"],
      "competitors": [
        {
          "name": "string",
          "website": "string or null",
          "main_service": "string",
          "target_market": "string",
          "strengths": ["string"],
          "weaknesses": ["string"],
          "source": "web_research | ai_suggested"
        }
      ],
      "strengths": ["string"],
      "opportunities": ["string"]
    },
    "target_search_queries": [
      {
        "query": "string",
        "platforms": ["Google", "LinkedIn"],
        "intent": "string",
        "business_relevance": "string",
        "target_audience": "string"
      }
    ],
    "seo_improvements": {
      "primary_keyword": "string",
      "secondary_keywords": ["string"],
      "long_tail_keywords": ["string"],
      "business_keywords": ["string"],
      "recommended_title": "string (50-60 chars ideal, include primary keyword)",
      "title_structure": "string (e.g. Primary Keyword - Value Proposition | Brand)",
      "meta_description": "string (140-160 chars, human-friendly with keywords)",
      "supporting_content": ["string"]
    },
    "top_services": [
      {
        "service_name": "string",
        "description": "string",
        "target_industry": "string",
        "target_customer": "string",
        "main_benefit": "string",
        "is_inferred": false
      }
    ],
    "target_audience": {
      "primary_audience": ["string"],
      "secondary_audience": ["string"],
      "industries": ["string"],
      "business_types": ["string"],
      "customer_profiles": ["string"],
      "geographical_focus": "string or null",
      "customer_needs": ["string"],
      "customer_interests": ["string"],
      "marketing_segments": ["string"]
    }
  }
}"""


class LLMServiceError(RuntimeError):
    """Raised when no configured LLM provider can complete the analysis."""


def extract_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise LLMServiceError("LLM returned malformed JSON output.") from exc

    raise LLMServiceError("LLM response did not contain a valid JSON object.")


def normalize_llm_payload(payload: dict[str, Any], has_web_hints: bool) -> dict[str, Any]:
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return payload

    queries = analysis.get("target_search_queries")
    if isinstance(queries, list):
        for item in queries:
            if not isinstance(item, dict):
                continue
            raw_platforms = item.get("platforms") or []
            normalized: list[str] = []
            for p in raw_platforms:
                mapped = SUPPORTED_PLATFORMS.get(str(p).strip().lower())
                if mapped and mapped not in normalized:
                    normalized.append(mapped)
            item["platforms"] = normalized or ["Google"]

    comp_section = analysis.get("competitor_analysis")
    if isinstance(comp_section, dict) and isinstance(comp_section.get("competitors"), list):
        for comp in comp_section["competitors"]:
            if not isinstance(comp, dict):
                continue
            src = str(comp.get("source", "")).strip().lower()
            if src == "web_research" and has_web_hints:
                comp["source"] = "web_research"
            else:
                comp["source"] = "ai_suggested"

    return payload


class LLMAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def analyze_website(
        self,
        website_context: str,
        competitor_hints: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        user_prompt = website_context
        has_hints = bool(competitor_hints)
        if competitor_hints:
            formatted_hints = "\n".join(
                f"- {h['title']}: {h['snippet']} ({h['link']})" for h in competitor_hints
            )
            user_prompt += f"\n\nLive Search Competitor Hints:\n{formatted_hints}"

        providers = self._provider_order()
        if not providers:
            raise LLMServiceError(
                "No LLM API key configured. Set GEMINI_API_KEY or OPENAI_API_KEY in .env."
            )

        last_err: Exception | None = None
        for provider in providers:
            try:
                if provider == "gemini":
                    raw = await self._call_gemini(user_prompt)
                else:
                    raw = await self._call_openai(user_prompt)
                data = extract_json_object(raw)
                return normalize_llm_payload(data, has_web_hints=has_hints)
            except Exception as exc:
                logger.warning("LLM provider '%s' failed: %s", provider, exc)
                last_err = exc

        raise LLMServiceError(f"LLM analysis failed: {last_err}")

    def _provider_order(self) -> list[str]:
        preferred = self.settings.llm_provider.strip().lower()
        available: list[str] = []
        if preferred == "openai":
            if self.settings.openai_api_key.strip():
                available.append("openai")
            if self.settings.gemini_api_key.strip():
                available.append("gemini")
        else:
            if self.settings.gemini_api_key.strip():
                available.append("gemini")
            if self.settings.openai_api_key.strip():
                available.append("openai")
        return available

    async def _call_gemini(self, user_prompt: str) -> str:
        model = self.settings.gemini_model.strip() or "gemini-3.8-flash"
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        )
        body = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        data = await self._post_with_retry(
            url=endpoint,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.settings.gemini_api_key.strip(),
            },
            json_body=body,
        )
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMServiceError("Gemini returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(
            str(p.get("text", "")) for p in parts if not p.get("thought")
        ).strip()
        if not text:
            raise LLMServiceError("Gemini returned an empty response body.")
        return text

    async def _call_openai(self, user_prompt: str) -> str:
        model = self.settings.openai_model.strip() or "gpt-4o-mini"
        body = {
            "model": model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = await self._post_with_retry(
            url="https://api.openai.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.openai_api_key.strip()}",
            },
            json_body=body,
        )
        choices = data.get("choices") or []
        if not choices:
            raise LLMServiceError("OpenAI returned no choices.")
        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise LLMServiceError("OpenAI returned empty message content.")
        return str(content)

    async def _post_with_retry(
        self,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any],
        max_attempts: int = 2,
    ) -> dict[str, Any]:
        timeout = httpx.Timeout(self.settings.llm_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await client.post(url, headers=headers, json=json_body)
                except httpx.TimeoutException as exc:
                    if attempt == max_attempts:
                        raise LLMServiceError("LLM request timed out.") from exc
                    await asyncio.sleep(1.0 * attempt)
                    continue
                except httpx.RequestError as exc:
                    if attempt == max_attempts:
                        raise LLMServiceError(f"Network error calling LLM: {exc}") from exc
                    await asyncio.sleep(1.0 * attempt)
                    continue

                if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                    await asyncio.sleep(1.5 * attempt)
                    continue

                if resp.status_code >= 400:
                    detail = resp.text[:300]
                    raise LLMServiceError(f"Upstream LLM HTTP {resp.status_code}: {detail}")

                return resp.json()

        raise LLMServiceError("Exhausted retries calling LLM API.")
