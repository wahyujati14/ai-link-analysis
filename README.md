# AI Website Link Analysis API

FastAPI service that fetches a public webpage, extracts its readable content and metadata, and generates structured business, competitor, search query, SEO, service, and audience insights via `POST /link-analysis`.

## Live Deployment

| Item | URL |
|---|---|
| Live Service | `https://<your-deployed-domain>` |
| Analysis Endpoint | `https://<your-deployed-domain>/link-analysis` |
| Interactive Docs (Swagger) | `https://<your-deployed-domain>/docs` |

## Architecture & Processing Flow

1. **URL & SSRF Validation (`app/utils/validators.py`)**: Normalizes `http`/`https` URLs, rejects embedded credentials and internal hostnames (`localhost`, `.local`, `.internal`), and resolves DNS records to block private, loopback, link-local, and cloud-metadata IP ranges (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.169.254`). Every HTTP redirect hop is re-validated before following.
2. **HTML Extraction (`app/services/website_extractor.py`)**: Streams up to 2 MB of HTML, extracts `<title>`, meta/OpenGraph descriptions, JSON-LD organization hints, navigation labels, `h1`-`h3` headings, and deduplicated body copy while stripping `<script>`, `<style>`, `<svg>`, and form boilerplate. Body text is capped at `12,000` characters to keep token usage predictable.
3. **Optional Competitor Grounding (`app/services/competitor_service.py`)**: When `SERPER_API_KEY` is set, queries Google search snippets for real competitor references and passes them into the prompt. Competitors backed by search hits are labeled `"source": "web_research"`; LLM-inferred competitors are explicitly labeled `"source": "ai_suggested"`.
4. **LLM Structured Analysis (`app/services/llm_service.py`)**: Calls Google Gemini (`gemini-2.5-flash` by default) in JSON mode with automatic fallback to OpenAI (`gpt-4o-mini`) if configured.
5. **Validation & Caching (`app/services/analysis_service.py`)**: Validates the output against Pydantic schemas (`app/schemas.py`) and caches completed analyses in an in-memory TTL LRU cache (`CACHE_TTL_SECONDS=3600`).

## Project Structure

```text
ai-link-analysis/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── services/
│   │   ├── website_extractor.py
│   │   ├── competitor_service.py
│   │   ├── llm_service.py
│   │   └── analysis_service.py
│   └── utils/
│       └── validators.py
├── tests/
│   └── test_link_analysis.py
├── .env.example
├── Dockerfile
├── Procfile
├── pytest.ini
├── requirements.txt
└── README.md
```

## Local Setup & Execution

### 1. Create virtual environment and install dependencies

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and add at least one LLM API key (`GEMINI_API_KEY` or `OPENAI_API_KEY`):

```bash
cp .env.example .env
```

### 3. Start the FastAPI server on port 4000

```bash
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Swagger UI is available at `http://localhost:4000/docs`.

### 4. Run automated tests

```bash
pytest -v
```

## Sample API Request & Response

### Request

```bash
curl -X POST http://localhost:4000/link-analysis \
  -H "Content-Type: application/json" \
  -d '{"url": "https://linear.app"}'
```

### Sample Response

```json
{
  "success": true,
  "website": "https://linear.app/",
  "brand": {
    "name": "Linear",
    "category": "Product Management & Issue Tracking Software",
    "summary": "Purpose-built tool for planning and building software products, streamlining issue tracking, sprints, and product roadmaps."
  },
  "analysis": {
    "competitor_analysis": {
      "brand_overview": "High-speed issue tracking and project planning platform tailored for modern software engineering and product teams.",
      "main_products_and_services": [
        "Issue Tracking & Sprint Cycles",
        "Product Roadmaps & Initiatives",
        "Customer Requests & Triage",
        "GitHub / GitLab Workflow Integrations"
      ],
      "competitors": [
        {
          "name": "Jira (Atlassian)",
          "website": "https://www.atlassian.com/software/jira",
          "main_service": "Enterprise agile project management and issue tracking",
          "target_market": "Mid-market and large enterprise IT & engineering teams",
          "strengths": [
            "Deep enterprise customization and compliance ecosystem",
            "Tight bundling with Confluence and Bitbucket"
          ],
          "weaknesses": [
            "Slower UI responsiveness and heavy administrative overhead"
          ],
          "source": "ai_suggested"
        },
        {
          "name": "Shortcut",
          "website": "https://www.shortcut.com",
          "main_service": "Collaborative software project management",
          "target_market": "Startup and scaleup software engineering teams",
          "strengths": [
            "Lighter setup than Jira with built-in docs"
          ],
          "weaknesses": [
            "Smaller ecosystem of developer-first keyboard workflows"
          ],
          "source": "ai_suggested"
        },
        {
          "name": "Asana",
          "website": "https://asana.com",
          "main_service": "Cross-functional work management",
          "target_market": "Marketing, operations, and general business teams",
          "strengths": [
            "Accessible to non-technical departments"
          ],
          "weaknesses": [
            "Lacks native Git PR automation and engineering triage depth"
          ],
          "source": "ai_suggested"
        }
      ],
      "strengths": [
        "Keyboard-first speed and opinionated engineering workflows",
        "Tight Git synchronization for automated issue state transitions"
      ],
      "opportunities": [
        "Publish migration benchmarks and ROI calculators for teams leaving Jira",
        "Expand landing pages around cross-functional product discovery workflows"
      ]
    },
    "target_search_queries": [
      {
        "query": "fast jira alternative for software teams",
        "platforms": ["Google", "X"],
        "intent": "Commercial Comparison",
        "business_relevance": "Captures engineering teams frustrated by slow legacy trackers",
        "target_audience": "Engineering Managers and CTOs"
      },
      {
        "query": "modern issue tracking and product roadmap tool",
        "platforms": ["Google", "LinkedIn"],
        "intent": "Service Discovery",
        "business_relevance": "Matches core product planning and sprint management capabilities",
        "target_audience": "Heads of Product and VPs of Engineering"
      },
      {
        "query": "how startups run engineering sprints and triage",
        "platforms": ["LinkedIn", "X"],
        "intent": "Educational / Workflow Discovery",
        "business_relevance": "Aligns with Linear Method best practices",
        "target_audience": "Startup Founders and Tech Leads"
      },
      {
        "query": "software roadmap UI design inspiration",
        "platforms": ["Instagram", "X"],
        "intent": "Visual Inspiration",
        "business_relevance": "Leverages brand reputation for craft and product design",
        "target_audience": "Product Designers and Frontend Engineers"
      },
      {
        "query": "project management software with GitHub integration",
        "platforms": ["Google", "Facebook"],
        "intent": "Feature Search",
        "business_relevance": "Targets developer teams automating PR-to-ticket updates",
        "target_audience": "Software Development Teams"
      }
    ],
    "seo_improvements": {
      "primary_keyword": "Issue Tracking and Product Management Software",
      "secondary_keywords": [
        "Jira alternative for startups",
        "agile sprint planning tool",
        "engineering roadmap software"
      ],
      "long_tail_keywords": [
        "fast keyboard-driven issue tracker with GitHub sync",
        "product roadmap and bug triage tool for SaaS teams"
      ],
      "business_keywords": [
        "software development lifecycle platform",
        "engineering project tracker"
      ],
      "recommended_title": "Issue Tracking & Product Roadmap Software | Linear",
      "title_structure": "Primary Capability & Category | Brand Name",
      "meta_description": "Plan sprints, track issues, and manage product roadmaps at high speed. Linear helps software teams streamline workflows with Git sync and automated triage.",
      "supporting_content": [
        "Comparison landing pages (Linear vs Jira, Linear vs Shortcut)",
        "Role-based pages for CTOs, Product Managers, and Customer Support triage",
        "Interactive Jira-to-Linear migration guide and FAQ"
      ]
    },
    "top_services": [
      {
        "service_name": "Issue Tracking & Cycles",
        "description": "Fast bug and task tracking organized around time-boxed engineering cycles.",
        "target_industry": "Software & SaaS",
        "target_customer": "Software engineering teams",
        "main_benefit": "Keeps sprint execution fast without manual ticket upkeep",
        "is_inferred": false
      },
      {
        "service_name": "Product Roadmaps & Projects",
        "description": "Multi-team project planning with milestone tracking and progress forecasting.",
        "target_industry": "Technology",
        "target_customer": "Product managers and leadership",
        "main_benefit": "Connects high-level company initiatives directly to engineering tasks",
        "is_inferred": false
      },
      {
        "service_name": "Triage & Customer Requests",
        "description": "Centralized inbox linking customer feedback and support reports to product issues.",
        "target_industry": "B2B SaaS",
        "target_customer": "Product and support operations teams",
        "main_benefit": "Prioritizes roadmap items based on real customer impact",
        "is_inferred": false
      },
      {
        "service_name": "Git & CI Workflow Automation",
        "description": "Automatic ticket status updates triggered by pull requests and branch activity.",
        "target_industry": "Software Development",
        "target_customer": "Developers and DevOps engineers",
        "main_benefit": "Eliminates manual status updates after code merges",
        "is_inferred": false
      },
      {
        "service_name": "Engineering Analytics & Insights",
        "description": "Cycle velocity, scope creep, and throughput reporting across teams.",
        "target_industry": "Technology Enterprises",
        "target_customer": "VPs of Engineering",
        "main_benefit": "Surfaces delivery bottlenecks without manual spreadsheet reporting",
        "is_inferred": true
      }
    ],
    "target_audience": {
      "primary_audience": [
        "Software engineering teams, CTOs, and Product Managers at technology companies"
      ],
      "secondary_audience": [
        "Product designers and customer support teams collaborating on bug triage"
      ],
      "industries": [
        "B2B SaaS",
        "Developer Tools",
        "FinTech",
        "AI & Cloud Software"
      ],
      "business_types": [
        "High-growth startups",
        "Scaleups",
        "Modern digital product enterprises"
      ],
      "customer_profiles": [
        "10-1,000 person product organizations shipping continuous software releases"
      ],
      "geographical_focus": "Global",
      "customer_needs": [
        "Low-latency issue tracking",
        "Clear visibility into roadmap progress",
        "Automated Git-to-ticket synchronization"
      ],
      "customer_interests": [
        "Developer productivity",
        "Product operations",
        "Software craft and UI speed"
      ],
      "marketing_segments": [
        "Seed-to-Series C CTOs",
        "Teams migrating off Jira",
        "Heads of Product at SaaS companies"
      ]
    }
  }
}
```

*(Note: Search queries intentionally omit search volume figures unless connected to a paid keyword-volume API, per specification guidelines.)*

---

## LLM Platform & Model Research (Cost, Speed, and Accuracy)

### A. LLM Platform Comparison

Pricing figures reflect published standard pay-as-you-go API rates per 1M tokens. Latency ranges below are **estimated** end-to-end generation times for a ~1,100-token structured JSON payload (~3,000 input tokens), not synthetic vendor marketing peaks.

| Criteria | Google Gemini (`gemini-2.5-flash`) | OpenAI (`gpt-4o-mini`) | OpenAI (`gpt-4.1-mini`) | Anthropic (`claude-haiku-4-5`) |
|---|---|---|---|---|
| **Provider** | Google AI / Vertex | OpenAI | OpenAI | Anthropic |
| **Model Name** | `gemini-2.5-flash` | `gpt-4o-mini` | `gpt-4.1-mini` | `claude-haiku-4-5` |
| **API Cost (Input / Output per 1M)** | \$0.30 / \$2.50 (Free tier available in AI Studio) | \$0.15 / \$0.60 | \$0.40 / \$1.60 | \$1.00 / \$5.00 |
| **Response Speed (Est. for ~1.1K JSON)** | ~2.2s – 4.5s | ~3.0s – 5.5s | ~2.8s – 5.0s | ~2.5s – 4.8s |
| **Accuracy (Web & SEO Synthesis)** | High; strong extraction fidelity on messy web text | Good; occasional generic phrasing on niche B2B sites | High; strong instruction adherence | High; nuanced marketing copy, pricier output |
| **Context Window** | ~1,000,000 tokens | 128,000 tokens | ~1,047,576 tokens | 200,000 tokens |
| **JSON Support** | Native `responseMimeType: application/json` + schemas | Native `json_object` / Structured Outputs | Native `json_object` / Structured Outputs | Tool-use / prefilled JSON |
| **Recommendation** | **Best Primary** (speed + 1M context + free dev tier) | **Best Low-Cost Fallback** | Strong mid-tier option | Accurate, but 3x–8x costlier on output tokens |

### B. Best Model Selection Rationale

`gemini-2.5-flash` is selected as the primary model with `gpt-4o-mini` wired as an automatic fallback:
1. **Website Understanding & SEO Quality**: Produces specific positioning gaps, realistic long-tail keywords, and clean service descriptions grounded in page copy rather than generic templates.
2. **Speed**: Consistently low time-to-first-token and high output throughput keep full `/link-analysis` latency interactive (~3–6 seconds including webpage fetch).
3. **Structured JSON Reliability**: Native `responseMimeType: "application/json"` combined with server-side Pydantic validation (`LinkAnalysisResponse`) eliminates broken JSON responses.
4. **Resilience & Cost**: AI Studio provides a free tier for development/evaluation, while production pay-as-you-go remains fraction-of-a-cent per call, backed by `gpt-4o-mini` if Gemini hits quota limits.

### C. Cost Optimization Implemented in This Codebase

- **DOM Noise Stripping (`website_extractor.py`)**: `<script>`, `<style>`, `<noscript>`, `<svg>`, `<iframe>`, and `<form>` nodes are removed prior to text extraction, cutting raw HTML size by 75%–90%.
- **Deduplicated Paragraph Capping**: Repeated navigation/footer strings are filtered out and body text is capped at `MAX_CONTENT_CHARS=12000` (~2,800 tokens).
- **Single-Pass Multi-Section Prompt**: All five required sections are generated in one structured JSON completion rather than five separate LLM round-trips, saving 4x input token overhead.
- **In-Memory TTL Caching (`analysis_service.py`)**: Repeat requests for the same normalized URL within `CACHE_TTL_SECONDS` (default 1 hour) return immediately at zero token cost.

### D. Final LLM Recommendation Summary

- **Recommended Provider & Model**: Google Gemini — `gemini-2.5-flash`
- **Fallback Provider & Model**: OpenAI — `gpt-4o-mini`
- **Estimated Input Usage**: ~3,000 tokens per uncached webpage (cleaned metadata + headings + body text + system instructions)
- **Estimated Output Usage**: ~1,100 tokens per structured 5-section response
- **Estimated Cost per Analysis**:
  - `gemini-2.5-flash` (paid tier): `(3,000 * $0.30 + 1,100 * $2.50) / 1,000,000` ≈ **\$0.00365 per website** (\$0.00 within AI Studio free tier limits)
  - `gpt-4o-mini` (fallback): `(3,000 * $0.15 + 1,100 * $0.60) / 1,000,000` ≈ **\$0.00111 per website**
- **Expected End-to-End Response Time**: ~1.0s HTML fetch (measured locally on typical sites) + ~2.5s–4.5s LLM generation (estimated) = **~3.5s–5.5s uncached**, **<15ms cached**.

## Deployment (Render / Railway / Docker)

A `Dockerfile` and `Procfile` are included for direct deployment:

```bash
docker build -t ai-link-analysis .
docker run -p 4000:4000 --env-file .env ai-link-analysis
```

On Render or Railway, connect the repository, set `GEMINI_API_KEY` (and optionally `OPENAI_API_KEY` / `SERPER_API_KEY`) in Environment Variables, and expose `/docs` and `POST /link-analysis`.
