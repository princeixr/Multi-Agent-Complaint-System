# TriageAI

TriageAI is a supervisor-led, multi-agent complaint intelligence system for financial services. It does not stop at intake or classification. The codebase implements a full complaint operating model: conversational intake, document ingestion and OCR, agent orchestration, risk and root-cause analysis, compliance checks, routing, resolution planning, live traces, and evaluation infrastructure.

This repository documents an ongoing effort to build a complaint-handling platform that is structured, evidence-aware, inspectable, and extensible. The architecture shown on the home page is reflected in the implementation across the workflow, storage, retrieval, observability, and evaluation layers in this codebase.

## Project Overview

TriageAI is being developed as a complaint operations system for regulated environments where narrative intake alone is not enough. The central idea is that complaint handling should be treated as a coordinated operational process rather than a single-model classification task.

The project combines:

- structured intake
- document-aware complaint processing
- specialist agents for classification, risk, root cause, compliance, routing, review, and resolution
- persistent workflow traces and cost visibility
- retrieval over prior complaints and company knowledge
- evaluation tooling for both benchmark and production cases

## Guiding Idea

The guiding idea behind TriageAI is that complaint handling should evolve from a queue-based manual workflow into a system of coordinated judgment.

In practical terms, that means:

- complaints should be grounded in evidence, not only narrative
- specialist reasoning should be separated by responsibility
- orchestration should be explicit and reviewable
- operational decisions should leave a trace
- evaluation should be part of the product, not an afterthought

## Current State

Today, the repository already contains a working end-to-end foundation for that vision.

- A supervisor-led LangGraph workflow coordinates specialist agents.
- Complaint intake is available through chat, with optional voice support.
- Uploaded PDFs and images are stored, processed, and OCR'd when needed.
- Document summaries and contradiction checks are generated before downstream reasoning.
- Risk, root cause, compliance, routing, review, and resolution outputs are produced as structured system steps.
- Workflow runs, workflow steps, token usage, latency, and cost are persisted.
- Admin-facing trace, analytics, and evaluation pages are included in the product.
- Benchmark and production evaluation infrastructure already exists in the codebase.

## Architecture

The homepage architecture is the system architecture:

```mermaid
flowchart TD
    U[Complaint Intake<br/>chat or voice] --> D[Document Gate]
    D --> C[Document Consistency Check]
    C --> S[Supervisor]

    S --> CL[Classification Agent]
    S --> RK[Risk Agent]
    S --> CP[Compliance Agent]
    S --> RC[Root Cause Agent]
    S --> RT[Routing Agent]
    S --> RV[Review Agent]
    S --> RS[Resolution Agent]

    CL --> S
    RK --> S
    CP --> S
    RC --> S
    RT --> S
    RV --> S
    RS --> S

    S --> O[Persisted Outcome<br/>case status, route, severity]
    O --> T[Live Trace + Analytics + Evaluation]
```

### Supervisor-Led Agentic Flow

- `intake` normalizes and validates the case payload.
- `document_gate` waits for uploaded evidence to finish background processing.
- `check_document_consistency` compares the complaint narrative with extracted document facts.
- `supervisor` decides which specialist to run next.
- Specialists cover classification, risk, compliance, root cause, routing, review, and resolution.
- Final outputs are persisted with workflow metadata for later inspection.

The implementation lives in [app/orchestrator/workflow.py](app/orchestrator/workflow.py).

## How It Works

### 1. Intake And Evidence Processing

This system treats uploaded evidence as a first-class input, not an attachment afterthought.

- PDF text extraction for digital documents
- OCR for scanned PDFs via `pdftoppm` + `tesseract`
- OCR for screenshots and images
- fact extraction for amounts, dates, reference numbers, and signals
- document chunking and embeddings for downstream retrieval
- document-vs-narrative contradiction checks before agent reasoning

See [app/documents/service.py](app/documents/service.py).

### 2. Supervisor And Specialist Agents

The system has separate agents and schemas for:

- intake
- classification
- risk
- root cause
- resolution
- compliance
- review
- routing

This is backed by dedicated prompts, structured schemas, and a supervisor router across the `app/agents`, `app/prompts`, and `app/schemas` packages.

### 3. Retrieval And Knowledge Support

Retrieval is backed by PostgreSQL and pgvector, allowing the workflow to pull supporting context from stored complaint history and knowledge assets.

- complaint similarity search is backed by PostgreSQL + pgvector
- embeddings support local HuggingFace models or OpenAI
- retrieval can surface historical complaint patterns and company context

See [app/retrieval/complaint_index.py](app/retrieval/complaint_index.py) and [app/retrieval/ingest.py](app/retrieval/ingest.py).

### 4. Observability And Traceability

The workflow includes a persistent operational record of how each case moved through the system:

- workflow runs persisted to Postgres
- per-step snapshots and state diffs
- trace IDs and OpenTelemetry integration
- token, latency, and cost accounting
- version tracking for workflow, prompts, knowledge pack, and model
- admin UI for live trace inspection

See [app/observability/persistence.py](app/observability/persistence.py), [app/observability/tracing.py](app/observability/tracing.py), and [app/templates/trace.html](app/templates/trace.html).

### 5. Evaluation Layer

The evaluation layer supports both iterative development and ongoing operational review:

- database-backed evaluation datasets
- weak-gold label generation
- rubric-based LLM judge runs
- disagreement queues for human review
- production case evaluation against real workflow outputs

See [app/evals/service.py](app/evals/service.py) and [app/evals/judge.py](app/evals/judge.py).

### 6. Product Surface

The repo includes a server-rendered product, not only backend endpoints.

- public-facing marketing and home pages
- end-user lodge flow with conversational intake
- optional voice intake
- admin dashboards
- analytics and evaluation pages
- team and queue views
- case detail and resolution history pages

The UI templates live under [app/templates](app/templates).

## Achievements So Far

- Designed and implemented a supervisor-led multi-agent complaint workflow.
- Built document ingestion with OCR support for scanned PDFs and images.
- Added evidence summaries and narrative-to-document consistency checks.
- Implemented structured agent outputs for classification, risk, root cause, resolution, and compliance.
- Added workflow run persistence with step-level tracing, versioning, and cost rollups.
- Built retrieval infrastructure over complaint history using pgvector.
- Added production evaluation and benchmark evaluation workflows.
- Shipped admin-facing views for trace inspection, analytics, evaluations, and case review.

## Direction Of The Project

The project is moving toward a more complete complaint intelligence and governance system.

Near-term directions:

- deepen the knowledge layer used by risk and root-cause agents
- strengthen regulatory and policy grounding
- improve retrieval quality and evidence selection
- expand disagreement review and adjudication workflows
- tighten routing and operational ownership signals
- improve evaluation coverage on real complaint patterns

Longer-term directions:

- richer regulatory knowledge graphs and effective-dated policy context
- stronger precedent reasoning across historical complaint clusters
- deeper human-in-the-loop review and escalation controls
- more robust remediation guidance and operational feedback loops
- stronger enterprise reporting around quality, risk, and model behavior

## Repository Map

```text
app/
  agents/          specialist agents, supervisor, tools, LLM helpers
  api/             FastAPI endpoints and intake integrations
  db/              ORM models and session management
  documents/       upload persistence, OCR, extraction, summaries
  evals/           benchmark runners, judge, review services
  knowledge/       company knowledge and taxonomy context
  observability/   tracing, event logging, versioning, cost tracking
  orchestrator/    LangGraph workflow, rules, retrieval gates, state
  retrieval/       embeddings, ingest, pgvector-backed indexes
  schemas/         structured outputs for agents and cases
  templates/       product UI and admin views
  ui/              server-rendered routes and page context
tests/
architecture.md    deeper knowledge-base and regulatory architecture
```

## Product Highlights

- Supervisor-led LangGraph workflow
- complaint intake via chat with optional voice mode
- document-aware complaint processing
- scanned-PDF and image OCR
- complaint similarity retrieval with pgvector
- risk, root-cause, compliance, and routing agents
- live workflow trace UI
- production evaluation reports
- benchmark dataset and judge infrastructure
- website-friendly case IDs such as `CASE00001`

## Tech Stack

- Python 3.11+
- FastAPI
- Jinja2
- SQLAlchemy
- PostgreSQL
- pgvector
- LangGraph / LangChain
- OpenTelemetry
- OpenAI or DeepSeek
- optional ElevenLabs voice output

## Running Locally

### Prerequisites

- Python 3.11+
- PostgreSQL with `pgvector`
- one LLM provider configured: OpenAI or DeepSeek
- `tesseract` and `poppler` for OCR

Recommended:

- `uv`
- Docker

### Environment

```bash
cp .env.example .env
```

Minimum variables:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/complaints
LLM_PROVIDER=openai
OPENAI_API_KEY=...
```

DeepSeek option:

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
```

Useful optional variables:

- `OPENAI_CHAT_MODEL`
- `DEEPSEEK_CHAT_MODEL`
- `EMBEDDING_PROVIDER`
- `HF_EMBEDDING_MODEL`
- `TRACE_INTAKE_TO_LANGSMITH`
- `LANGCHAIN_TRACING_V2`
- `LANGCHAIN_API_KEY`
- `LANGCHAIN_PROJECT`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`

### Install

With `uv`:

```bash
uv sync
```

With `pip`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### OCR Dependencies

macOS:

```bash
brew install tesseract poppler
```

Ubuntu / Debian:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils
```

### Database

```bash
docker compose up db -d
```

### Start The App

```bash
python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

For a full local stack:

```bash
docker compose up --build -d
docker compose logs -f app
```

Historical workflow cost aggregates are backfilled on startup. You can also run that manually:

```bash
python3 scripts/backfill_cost_ledger.py
```

## Voice Intake

The lodge flow supports chat and optional voice mode.

- speech-to-text uses the browser Web Speech API
- spoken responses can use ElevenLabs when configured
- microphone access requires `localhost` or HTTPS

For local HTTPS:

```bash
./scripts/dev_https.sh
```

By default this serves `https://127.0.0.1:8001`. The certificate setup notes are in [scripts/dev_https.sh](scripts/dev_https.sh).

## Demo Accounts

Admin:

- email: `admin@triage.ai`
- password: `admin123`

End user:

- email: `user@triage.ai`
- password: `user123`

Team users:

- seeded automatically
- password pattern: `<local-part>123`
- reference: [Team Credentials](https://github.com/ayman-tech/Multi-Agent-Complaint-System/wiki/Team-Credentials)

## Further Reading

- [architecture.md](architecture.md)
- [repository_architecture.pdf](repository_architecture.pdf)
- [repository_architecture_detailed.pdf](repository_architecture_detailed.pdf)

## License

No license file is currently included in this repository. Treat usage and redistribution as private unless an explicit license is added.
