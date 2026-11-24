from collections import OrderedDict
import time

from pydantic import ValidationError

from app.config import Settings
from app.schemas import LinkAnalysisResponse
from app.services.competitor_service import fetch_competitor_hints
from app.services.llm_service import LLMAnalyzer, LLMServiceError
from app.services.website_extractor import fetch_and_extract
from app.utils.validators import validate_public_url

MAX_CACHE_ENTRIES = 128


class AnalysisService:
    def __init__(self, settings: Settings, llm_analyzer: LLMAnalyzer | None = None) -> None:
        self.settings = settings
        self.llm = llm_analyzer or LLMAnalyzer(settings)
        self._cache: OrderedDict[str, tuple[float, LinkAnalysisResponse]] = OrderedDict()

    def _get_cached(self, key: str) -> LinkAnalysisResponse | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        expires_at, response = entry
        if time.monotonic() > expires_at:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return response

    def _set_cached(self, key: str, response: LinkAnalysisResponse) -> None:
        if self.settings.cache_ttl_seconds <= 0:
            return
        self._cache[key] = (time.monotonic() + self.settings.cache_ttl_seconds, response)
        self._cache.move_to_end(key)
        while len(self._cache) > MAX_CACHE_ENTRIES:
            self._cache.popitem(last=False)

    async def analyze_url(self, raw_url: str) -> LinkAnalysisResponse:
        normalized_url = validate_public_url(raw_url)
        cached = self._get_cached(normalized_url)
        if cached is not None:
            return cached

        extracted = await fetch_and_extract(
            url=normalized_url,
            timeout_seconds=self.settings.request_timeout_seconds,
            max_chars=self.settings.max_content_chars,
        )

        competitor_hints = await fetch_competitor_hints(
            website_url=extracted.final_url,
            title=extracted.title,
            serper_api_key=self.settings.serper_api_key,
            timeout_seconds=min(self.settings.request_timeout_seconds, 10.0),
        )

        llm_result = await self.llm.analyze_website(
            website_context=extracted.to_prompt_context(),
            competitor_hints=competitor_hints,
        )

        try:
            validated = LinkAnalysisResponse.model_validate(
                {
                    "success": True,
                    "website": extracted.final_url,
                    "brand": llm_result.get("brand", {}),
                    "analysis": llm_result.get("analysis", {}),
                }
            )
        except ValidationError as exc:
            raise LLMServiceError(f"LLM output failed schema validation: {exc}") from exc

        self._set_cached(normalized_url, validated)
        return validated
