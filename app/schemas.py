from typing import Literal
from pydantic import BaseModel, Field, field_validator


class LinkAnalysisRequest(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048, examples=["https://stripe.com"])

    @field_validator("url")
    @classmethod
    def strip_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("URL must not be empty")
        return cleaned


class BrandInfo(BaseModel):
    name: str
    category: str
    summary: str


class CompetitorItem(BaseModel):
    name: str
    website: str | None = None
    main_service: str
    target_market: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    source: Literal["web_research", "ai_suggested"] = "ai_suggested"


class CompetitorAnalysis(BaseModel):
    brand_overview: str
    main_products_and_services: list[str] = Field(default_factory=list)
    competitors: list[CompetitorItem] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)


class TargetSearchQuery(BaseModel):
    query: str
    platforms: list[str] = Field(default_factory=list)
    intent: str
    business_relevance: str = ""
    target_audience: str = ""


class SeoImprovements(BaseModel):
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    long_tail_keywords: list[str] = Field(default_factory=list)
    business_keywords: list[str] = Field(default_factory=list)
    recommended_title: str
    title_structure: str = ""
    meta_description: str
    supporting_content: list[str] = Field(default_factory=list)


class ServiceItem(BaseModel):
    service_name: str
    description: str
    target_industry: str
    target_customer: str
    main_benefit: str
    is_inferred: bool = False


class TargetAudience(BaseModel):
    primary_audience: list[str] = Field(default_factory=list)
    secondary_audience: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    business_types: list[str] = Field(default_factory=list)
    customer_profiles: list[str] = Field(default_factory=list)
    geographical_focus: str | None = None
    customer_needs: list[str] = Field(default_factory=list)
    customer_interests: list[str] = Field(default_factory=list)
    marketing_segments: list[str] = Field(default_factory=list)


class WebsiteAnalysisSections(BaseModel):
    competitor_analysis: CompetitorAnalysis
    target_search_queries: list[TargetSearchQuery]
    seo_improvements: SeoImprovements
    top_services: list[ServiceItem]
    target_audience: TargetAudience


class LinkAnalysisResponse(BaseModel):
    success: bool = True
    website: str
    brand: BrandInfo
    analysis: WebsiteAnalysisSections


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: str | None = None
