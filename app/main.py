import logging

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.schemas import ErrorResponse, LinkAnalysisRequest, LinkAnalysisResponse
from app.services.analysis_service import AnalysisService
from app.services.llm_service import LLMServiceError
from app.services.website_extractor import WebsiteFetchError
from app.utils.validators import URLValidationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = FastAPI(
    title="AI Website Link Analysis API",
    description="Extracts website content and generates brand, competitor, SEO, service, and audience insights.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_service_instance: AnalysisService | None = None


def get_analysis_service(settings: Settings = Depends(get_settings)) -> AnalysisService:
    global _service_instance
    if _service_instance is None:
        _service_instance = AnalysisService(settings=settings)
    else:
        _service_instance.settings = settings
        _service_instance.llm.settings = settings
    return _service_instance


@app.exception_handler(URLValidationError)
async def handle_url_validation_error(_: Request, exc: URLValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(error="Invalid or restricted URL", detail=str(exc)).model_dump(),
    )


@app.exception_handler(WebsiteFetchError)
async def handle_website_fetch_error(_: Request, exc: WebsiteFetchError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content=ErrorResponse(error="Website inaccessible", detail=str(exc)).model_dump(),
    )


@app.exception_handler(LLMServiceError)
async def handle_llm_error(_: Request, exc: LLMServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(error="Analysis engine unavailable", detail=str(exc)).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    messages = "; ".join(err.get("msg", "Invalid field") for err in exc.errors())
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error="Invalid request payload", detail=messages).model_dump(),
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "AI Website Link Analysis API",
        "status": "running",
        "endpoint": "POST /link-analysis",
        "docs": "/docs",
    }


@app.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "status": "ok",
        "llm_configured": bool(settings.gemini_api_key or settings.openai_api_key),
    }


@app.post(
    "/link-analysis",
    response_model=LinkAnalysisResponse,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def analyze_link(
    payload: LinkAnalysisRequest,
    service: AnalysisService = Depends(get_analysis_service),
) -> LinkAnalysisResponse:
    return await service.analyze_url(payload.url)
