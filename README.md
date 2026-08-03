# Codegate

A governance layer for AI coding agents: an orchestrator plans and
retrieves grounding context (RAG over the target repo), a codegen agent
produces a patch, a validator agent scores it (static analysis, tests,
LLM judge), and a guardrail gate routes the result to auto-merge, human
review, or reject before it ever reaches CI/CD. Every hop is traced with
OpenTelemetry and surfaced in Grafana.

Built to mirror what an "Ace Frontier Engineer"-type role actually ships:
multi-agent orchestration, RAG pipelines, validating AI-generated code,
quality gates in CI/CD, and observability/guardrails for agents in
production — not a demo chatbot.

## Architecture

```
intent -> orchestrator (plan + retrieve) -> codegen -> validator -> guardrail
                                                                       |
                                              auto-merge <-------------+-------------> human review
                                                  |                                        |
                                            CI/CD quality gate                     dashboard queue
```

## Services

| Service      | Port | Responsibility |
|--------------|------|-----------------|
| gateway      | 8000 | entry point, chains the pipeline, GitHub webhook receiver |
| orchestrator | 8001 | LangGraph: parses intent, retrieves context, plans steps |
| retrieval    | 8002 | RAG: indexes the target repo into pgvector, serves retrieval |
| codegen      | 8003 | calls an LLM to turn a Plan into a diff |
| validator    | 8004 | static analysis + tests + LLM judge -> confidence score |
| guardrail    | 8005 | policy engine: auto-merge / human review / reject |
| dashboard    | 3000 | Next.js review queue + embedded Grafana metrics |

`shared/` holds the pydantic schemas every service passes back and
forth, the OpenTelemetry bootstrap, and the LLM client interface.

## Running locally

```bash
cp .env.example .env
# then in .env:
#   1. set POSTGRES_PASSWORD (required — compose refuses to start without it)
#      and use the same password inside DATABASE_URL
#   2. add your free OpenRouter API key (openrouter.ai, no card needed)
#   3. replace the GATEWAY_API_KEY / GITHUB_WEBHOOK_SECRET placeholders
docker compose up --build
```

All LLM calls go to OpenRouter free-tier models online (DeepSeek V3 for
codegen, DeepSeek R1 for escalation retries, Gemini Flash as the judge,
Llama 3.3 70B as the planner) — different families on purpose, so the
judge never rubber-stamps the model that wrote the patch. Override any
route with `CODEGEN_MODEL` / `ESCALATION_MODEL` / `JUDGE_MODEL` /
`PLANNER_MODEL` in `.env`.

Then index a target repo and submit an intent:

```bash
python scripts/index_repo.py --repo punrek --path /path/to/punrek

curl -X POST http://localhost:8000/intents \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me' \
  -d '{"intent_id": "i1", "repo": "punrek", "prompt": "add rate limiting to the auth endpoint", "submitted_by": "mrinal"}'
```

Dashboard: http://localhost:3000
Grafana:   http://localhost:3001 (import `observability/grafana/dashboards/agent-pipeline.json`)

## Build order (MVP first)

1. `shared/` schemas + otel setup — done, this is the contract everything else follows
2. `retrieval` — get indexing + retrieval working against one real repo
3. `codegen` — one model, no routing yet, just prompt -> diff
4. `validator` — static checks + pytest first, LLM judge second
5. `guardrail` — one threshold rule, no sensitive-path policy yet
6. `gateway` — wire the four together, no webhook yet, just the `/intents` endpoint
7. Get one real PR merged end to end against a real repo
8. Then: dashboard, GitHub webhook, sensitive-path policy, Grafana dashboard, model routing/escalation

Steps 1-7 are the buildable MVP. Everything in step 8 is what turns this
from "it runs" into "it's a portfolio piece with a governance story."

## What's stubbed vs real

Every service has real FastAPI wiring, real pydantic contracts, and real
tests for the parts that don't need an LLM call. The formerly-stubbed
pieces are now implemented: LLM calls go through OpenRouter free-tier
models (`shared/llm_clients.py`), the tree-sitter chunking in
`retrieval/app/indexer.py` works (with regex and fixed-size fallbacks),
and the validator applies diffs to a hermetic scratch clone in
`validator/app/scoring.py`. The gateway enforces API-key auth on
`/intents`, the GitHub webhook verifies HMAC-SHA256 signatures and maps
labeled issues to intents, codegen escalates to a stronger model on
failed validation, the planner proposes real multi-step plans, the judge
takes a median over samples, and the human-review queue is SQLite-backed
with approve/reject endpoints.

Still open: `scripts/seed_eval_set.py` (calibrating the confidence
thresholds against real merged PRs) and swapping the commit-to-scratch
"auto-merge" for opening a real GitHub PR.
