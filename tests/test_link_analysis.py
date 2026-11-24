from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import app, get_analysis_service
from app.services.analysis_service import AnalysisService
from app.services.website_extractor import (
    ExtractedWebsite,
    WebsiteFetchError,
    parse_html_content,
)
from app.utils.validators import URLValidationError, validate_public_url


SAMPLE_HTML = """
<!doctype html>
<html lang="en">
<head>
  <title>Northstar Cloud | Managed DevOps & Kubernetes Consulting</title>
  <meta name="description" content="Northstar Cloud helps SaaS startups automate AWS, Kubernetes, and CI/CD pipelines.">
  <meta property="og:site_name" content="Northstar Cloud">
  <script type="application/ld+json">
    {"@type": "Organization", "name": "Northstar Cloud", "description": "Cloud & DevOps consultancy"}
  </script>
</head>
<body>
  <nav>
    <a href="/services/kubernetes">Kubernetes Management</a>
    <a href="/services/cicd">CI/CD Automation</a>
    <a href="/pricing">Pricing</a>
  </nav>
  <main>
    <h1>Production-Ready Cloud Infrastructure for High-Growth Startups</h1>
    <h2>Core Engineering Services</h2>
    <p>We design, migrate, and operate resilient AWS and GCP workloads with 24/7 SRE support and SOC2 readiness.</p>
    <p>Our engineers cut cloud spend by 30% while eliminating deployment bottlenecks for B2B SaaS teams.</p>
  </main>
  <script>console.log("ignore analytics noise");</script>
</body>
</html>
"""


def _sample_llm_payload() -> dict[str, Any]:
    return {
        "brand": {
            "name": "Northstar Cloud",
            "category": "Cloud & DevOps Consulting",
            "summary": "Cloud consultancy helping SaaS teams manage AWS, GCP, Kubernetes, and CI/CD infrastructure.",
        },
        "analysis": {
            "competitor_analysis": {
                "brand_overview": "Boutique DevOps partner focused on B2B SaaS startups and SOC2-ready infrastructure.",
                "main_products_and_services": [
                    "Kubernetes Management",
                    "CI/CD Automation",
                    "Cloud Cost Optimization",
                ],
                "competitors": [
                    {
                        "name": "Rackspace Technology",
                        "website": "https://www.rackspace.com",
                        "main_service": "Managed multi-cloud operations",
                        "target_market": "Mid-market and enterprise IT",
                        "strengths": ["Global enterprise footprint", "Broad vendor partnerships"],
                        "weaknesses": ["Higher contract minimums for early-stage startups"],
                        "source": "ai_suggested",
                    },
                    {
                        "name": " DoiT International",
                        "website": "https://www.doit.com",
                        "main_service": "Cloud FinOps and managed cloud consulting",
                        "target_market": "Cloud-native scaleups",
                        "strengths": ["Proprietary FinOps tooling"],
                        "weaknesses": ["Less hands-on custom CI/CD implementation"],
                        "source": "ai_suggested",
                    },
                    {
                        "name": "Contino",
                        "website": "https://www.contino.io",
                        "main_service": "Enterprise DevOps transformation",
                        "target_market": "Regulated enterprises",
                        "strengths": ["Deep compliance track record"],
                        "weaknesses": ["Overbuilt engagement model for seed/Series A teams"],
                        "source": "ai_suggested",
                    },
                ],
                "strengths": ["Startup-focused agility", "SOC2 readiness bundled with SRE"],
                "opportunities": ["Publish AWS cost benchmark case studies", "Add Terraform starter kits"],
            },
            "target_search_queries": [
                {
                    "query": "managed kubernetes consulting for startups",
                    "platforms": ["Google", "LinkedIn"],
                    "intent": "Service Discovery",
                    "business_relevance": "Directly matches core Kubernetes offering",
                    "target_audience": "SaaS CTOs and VPs of Engineering",
                },
                {
                    "query": "SOC2 compliant AWS infrastructure consultants",
                    "platforms": ["Google", "LinkedIn"],
                    "intent": "Commercial Investigation",
                    "business_relevance": "Captures compliance-driven cloud buyers",
                    "target_audience": "B2B SaaS founders preparing for enterprise deals",
                },
                {
                    "query": "how to cut AWS cloud spend SaaS",
                    "platforms": ["Google", "X"],
                    "intent": "Problem Solving",
                    "business_relevance": "Aligns with 30% cost reduction value proposition",
                    "target_audience": "Engineering managers",
                },
                {
                    "query": "DevOps agency CI/CD pipeline automation",
                    "platforms": ["LinkedIn", "Facebook"],
                    "intent": "Vendor Comparison",
                    "business_relevance": "Targets teams with release bottlenecks",
                    "target_audience": "Startup technical leads",
                },
                {
                    "query": "cloud architecture tips for scaling startups",
                    "platforms": ["Instagram", "X"],
                    "intent": "Educational Discovery",
                    "business_relevance": "Top-of-funnel brand awareness",
                    "target_audience": "Indie hackers and early founders",
                },
            ],
            "seo_improvements": {
                "primary_keyword": "Managed DevOps Consulting for Startups",
                "secondary_keywords": [
                    "Kubernetes consulting services",
                    "AWS cost optimization",
                    "CI/CD pipeline automation",
                ],
                "long_tail_keywords": [
                    "managed kubernetes and SOC2 readiness for B2B SaaS",
                    "outsource DevOps engineering for Series A startups",
                ],
                "business_keywords": ["SRE as a service", "cloud migration partner"],
                "recommended_title": "Managed DevOps & Kubernetes Consulting | Northstar Cloud",
                "title_structure": "Primary Keyword & Core Capability | Brand Name",
                "meta_description": "Scale on AWS and GCP with Northstar Cloud. Managed Kubernetes, CI/CD automation, SOC2 readiness, and 24/7 SRE built for high-growth SaaS startups.",
                "supporting_content": [
                    "Dedicated SOC2 Compliance on AWS landing page",
                    "Case study showing 30% cloud cost reduction breakdown",
                    "FAQ comparing Fractional SRE vs in-house DevOps hiring",
                ],
            },
            "top_services": [
                {
                    "service_name": "Kubernetes Management",
                    "description": "Design and 24/7 operation of production Kubernetes clusters.",
                    "target_industry": "B2B SaaS",
                    "target_customer": "Seed to Series B startups",
                    "main_benefit": "High availability without hiring a full platform team",
                    "is_inferred": False,
                },
                {
                    "service_name": "CI/CD Pipeline Automation",
                    "description": "Automated build, test, and zero-downtime deployment workflows.",
                    "target_industry": "Software & Technology",
                    "target_customer": "Fast-shipping product teams",
                    "main_benefit": "Eliminates manual release bottlenecks",
                    "is_inferred": False,
                },
                {
                    "service_name": "Cloud Cost Optimization",
                    "description": "Right-sizing compute, storage, and commitment plans on AWS/GCP.",
                    "target_industry": "Cloud-native startups",
                    "target_customer": "CTOs and Finance leads",
                    "main_benefit": "Reduces monthly cloud bills by roughly 30%",
                    "is_inferred": False,
                },
                {
                    "service_name": "SOC2 Infrastructure Readiness",
                    "description": "Hardening cloud security controls, logging, and IAM policies.",
                    "target_industry": "B2B FinTech and HealthTech",
                    "target_customer": "Startups closing enterprise contracts",
                    "main_benefit": "Accelerates security audits",
                    "is_inferred": False,
                },
                {
                    "service_name": "Infrastructure-as-Code Audits",
                    "description": "Review and modularize Terraform/OpenTofu stacks.",
                    "target_industry": "Technology",
                    "target_customer": "Scaling engineering orgs",
                    "main_benefit": "Prevents configuration drift across environments",
                    "is_inferred": True,
                },
            ],
            "target_audience": {
                "primary_audience": ["CTOs and VPs of Engineering at B2B SaaS startups"],
                "secondary_audience": ["Non-technical startup founders needing fractional SRE"],
                "industries": ["B2B SaaS", "FinTech", "Developer Tools"],
                "business_types": ["Venture-backed startups", "Cloud-native SMBs"],
                "customer_profiles": ["10-100 employee product companies outgrowing Heroku/PaaS"],
                "geographical_focus": "Global / Remote English-speaking markets",
                "customer_needs": ["Reliable uptime", "SOC2 audit preparation", "Lower AWS bills"],
                "customer_interests": ["Kubernetes", "DevSecOps", "Cloud FinOps"],
                "marketing_segments": ["Series A SaaS CTOs", "AWS Activate alumni"],
            },
        },
    }


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://localhost:8000/admin",
        "http://127.0.0.1/secret",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.15/internal",
        "http://192.168.1.1/",
        "ftp://example.com/file.txt",
        "file:///etc/passwd",
        "https://user:pass@example.com/",
    ],
)
def test_ssrf_and_scheme_validation_blocks_restricted_targets(blocked_url: str) -> None:
    with pytest.raises(URLValidationError):
        validate_public_url(blocked_url, resolve_dns=False)


def test_parse_html_extracts_clean_metadata_and_strips_scripts() -> None:
    extracted = parse_html_content(
        html=SAMPLE_HTML,
        requested_url="https://northstar.example.com",
        final_url="https://northstar.example.com/",
    )
    assert "Northstar Cloud" in extracted.title
    assert "SaaS startups" in extracted.meta_description
    assert "Kubernetes Management" in extracted.nav_items
    assert any("Production-Ready Cloud" in h for h in extracted.headings)
    assert "ignore analytics noise" not in extracted.body_text
    assert "30%" in extracted.body_text


def test_link_analysis_endpoint_returns_five_sections_and_uses_cache() -> None:
    mock_llm = AsyncMock()
    mock_llm.analyze_website.return_value = _sample_llm_payload()

    settings = Settings(gemini_api_key="test-key", cache_ttl_seconds=300)
    service = AnalysisService(settings=settings, llm_analyzer=mock_llm)
    app.dependency_overrides[get_analysis_service] = lambda: service

    extracted_site = parse_html_content(
        html=SAMPLE_HTML,
        requested_url="https://example.com",
        final_url="https://example.com/",
    )

    try:
        with (
            patch(
                "app.services.analysis_service.validate_public_url",
                return_value="https://example.com/",
            ),
            patch(
                "app.services.analysis_service.fetch_and_extract",
                new=AsyncMock(return_value=extracted_site),
            ) as mock_fetch,
        ):
            client = TestClient(app)
            first = client.post("/link-analysis", json={"url": "https://example.com"})
            assert first.status_code == 200
            body = first.json()
            assert body["success"] is True
            assert body["brand"]["name"] == "Northstar Cloud"
            assert len(body["analysis"]["competitor_analysis"]["competitors"]) == 3
            assert len(body["analysis"]["target_search_queries"]) == 5
            assert len(body["analysis"]["top_services"]) == 5
            assert body["analysis"]["seo_improvements"]["primary_keyword"]
            assert body["analysis"]["target_audience"]["primary_audience"]

            # Second identical request should be served from TTL cache
            second = client.post("/link-analysis", json={"url": "https://example.com"})
            assert second.status_code == 200
            assert mock_fetch.await_count == 1
            assert mock_llm.analyze_website.await_count == 1
    finally:
        app.dependency_overrides.clear()


def test_link_analysis_rejects_ssrf_with_400() -> None:
    client = TestClient(app)
    resp = client.post("/link-analysis", json={"url": "http://169.254.169.254/latest/meta-data"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["success"] is False


def test_link_analysis_handles_unreachable_website_with_502() -> None:
    settings = Settings(gemini_api_key="test-key", cache_ttl_seconds=0)
    service = AnalysisService(settings=settings, llm_analyzer=AsyncMock())
    app.dependency_overrides[get_analysis_service] = lambda: service

    try:
        with (
            patch(
                "app.services.analysis_service.validate_public_url",
                return_value="https://down.example.com/",
            ),
            patch(
                "app.services.analysis_service.fetch_and_extract",
                new=AsyncMock(side_effect=WebsiteFetchError("Connection refused")),
            ),
        ):
            client = TestClient(app)
            resp = client.post("/link-analysis", json={"url": "https://down.example.com"})
            assert resp.status_code == 502
            assert resp.json()["success"] is False
    finally:
        app.dependency_overrides.clear()
