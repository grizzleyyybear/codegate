# Codegate

A governance layer for AI coding agents: an orchestrator plans and pulls
grounding context (RAG over the target repo), a codegen agent produces a
patch, a validator agent scores it (static analysis, tests, LLM judge),
and a guardrail gate routes the result to auto-merge, human review, or
reject before it ever reaches CI/CD. Every hop is traced with
OpenTelemetry and surfaced in Grafana.

Built to mirror what an "Ace Frontier Engineer"-type role actually ships:
multi-agent orchestration, RAG pipelines, validating AI-generated code,
quality gates in CI/CD, and observability/guardrails for agents in
production — not a demo chatbot.

## Architecture

```
intent -> orchestrator (parse -> retrieve -> plan) -> codegen -> validator -> guardrail
                                                                                 |
                                  auto-merge (commit to scratch/<repo>) <---------+---------> human review
                                        |                                                       |
                                  CI/CD quality gate                                   dashboard queue
```

The orchestrator is a LangGraph: it heuristically scopes the intent,
retrieves grounding chunks from pgvector, optionally spawns a research
sub-agent when the first retrieval pass is weak, and plans multi-step
work with an LLM. The codegen agent rewrites whole files from the
retrieved context (no free-form "find the file" mode — the plan's
context IS the ground truth). If validation fails, the gateway retries
with full failure feedback and a stronger escalation model, then replans
the goal around the failure.

## Services

| Service      | Port | Responsibility |
|--------------|------|----------------|
| gateway      | 8000 | entry point, chains the pipeline, GitHub webhook receiver |
| orchestrator | 8001 | LangGraph: parses intent, retrieves context, plans steps |
| retrieval    | 8002 | RAG: indexes the target repo into pgvector, serves retrieval |
| codegen      | 8003 | calls an LLM to turn a Plan into a diff |
| validator    | 8004 | static analysis + tests + LLM judge -> confidence score |
| guardrail    | 8005 | policy engine: auto-merge / human review / reject |
| dashboard    | 3000 | Next.js review queue + embedded Grafana metrics |
| grafana      | 3001 | per-stage OTel traces and metrics |
| prometheus   | 9090 | metrics backend |
| otel-collector | 4317 / 8889 | trace/metrics collection |
| postgres     | 5432 | pgvector (retrieval embeddings) |
| ollama       | 11434 | optional offline fallback (`--profile offline`; unused by default) |

`shared/` holds the pydantic schemas every service passes back and
forth, the OpenTelemetry bootstrap, and the LLM client interface.

## Models

All LLM calls go to OpenRouter free-tier models online — different
families on purpose, so the judge never rubber-stamps the model that
wrote the patch. These slugs were verified live against OpenRouter
(2026-08); the older llama/gemini/deepseek `:free` endpoints are gone.
Override any route via env:

| Role | Default model |
|------|---------------|
| codegen default | `cohere/north-mini-code:free` (`CODEGEN_MODEL`) |
| codegen escalation | `nvidia/nemotron-3-super-120b-a12b:free` (`ESCALATION_MODEL`) |
| judge | `google/gemma-4-26b-a4b-it:free` (`JUDGE_MODEL`) |
| planner / researcher | `google/gemma-4-26b-a4b-it:free` (`PLANNER_MODEL`) |

## Running locally

```bash
cp .env.example .env
# then in .env:
#   1. set POSTGRES_PASSWORD (required — compose refuses to start without it)
#      and use the same password inside DATABASE_URL
#   2. add your free OpenRouter API key (openrouter.ai, no card needed)
#   3. replace the GATEWAY_API_KEY / GITHUB_WEBHOOK_SECRET placeholders
docker compose up --build -d
```

The stack is ready when every container reports healthy (compose starts
each service only after its dependencies pass health checks).

### 1. Seed a target repo

Put a git checkout of the repo you want to improve under `./scratch/`
(that directory is bind-mounted into the containers at `/work/` and is
gitignored). The `create_scratch_repo.py` script seeds a small sample
repo; for a real target, clone it:

```bash
git clone https://github.com/owner/repo scratch/myrepo
```

### 2. Index it

```bash
python scripts/index_repo.py --repo myrepo --path /work/myrepo
```

`--path` is resolved inside the retrieval container, so always point it
at `/work/<repo-dir>` even though the checkout lives at
`./scratch/<repo-dir>` on the host.

### 3. Submit an intent

```bash
curl -X POST http://localhost:8000/intents \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me' \
  -d '{"intent_id": "i1", "repo": "myrepo", "prompt": "add rate limiting to the auth endpoint", "submitted_by": "you"}'
```

The response returns the patch, validation results, the guardrail
decision, and the merge outcome. The pipeline runs synchronously — free
tier model latency means it can take several minutes (the gateway
allows up to 15 min per request; tune with `GATEWAY_REQUEST_TIMEOUT`).

### 4. See the result

- `git -C scratch/myrepo log` — the auto-merged commit
  (`codegate: <intent_id> via <model_used>`)
- Review queue / dashboard: http://localhost:3000
- Traces: http://localhost:3001 (import `observability/grafana/dashboards/agent-pipeline.json`)

Human review: `POST /reviews/{intent_id}` with `{"approve": true}`
applies the queued patch; `{"approve": false}` discards it — both
verdicts are recorded into the orchestrator's task memory so future
plans start with the lesson.

There is also a one-shot demo that seeds a sample repo, indexes it, and
submits a good and a bad intent end to end:

```bash
python scripts/e2e_demo.py
```

## GitHub webhook (optional)

`POST /webhooks/github` receives GitHub `issues` events and runs the
pipeline for any issue labeled `codegate` (label configurable via
`CODEGATE_TRIGGER_LABEL`). Signatures are verified with HMAC-SHA256
against `GITHUB_WEBHOOK_SECRET`; events are refused, not ignored, when
the secret is unset.

## Guardrail policy

The validator's aggregate confidence (static analysis pass, tests pass,
and an LLM judge scoring a median over samples) drives the gate:
`>= 0.85` auto-merges, `< 0.35` rejects, everything in between goes to
the human review queue. Thresholds are env-driven
(`AUTO_MERGE_THRESHOLD`, `REJECT_THRESHOLD`). Static analysis is
baseline-diffed: pre-existing ruff/mypy/bandit debt in the repo does not
block a merge — only new violations in the patch do.

## Testing

Each service tests independently; shared code is importable from any of
them via `PYTHONPATH`:

```powershell
# PowerShell
$env:PYTHONPATH = "services\gateway;shared"; python -m pytest services/gateway/tests -q
$env:PYTHONPATH = "services\orchestrator;shared"; python -m pytest services/orchestrator/tests -q
$env:PYTHONPATH = "services\retrieval;shared"; python -m pytest services/retrieval/tests -q
$env:PYTHONPATH = "services\codegen;shared"; python -m pytest services/codegen/tests -q
$env:PYTHONPATH = "services\validator;shared"; python -m pytest services/validator/tests -q
$env:PYTHONPATH = "services\guardrail;shared"; python -m pytest services/guardrail/tests -q
```

Lint and types: `ruff check services shared` and `mypy --python-version 3.11`.

## What's real vs stubbed

Real: every service is a real FastAPI app with real pydantic contracts.
LLM calls go through OpenRouter free-tier models, retrieval chunking is
tree-sitter-based with regex and fixed-size fallbacks, embeddings live
in pgvector, the validator applies each patch to a hermetic scratch
clone of the repo before running ruff/mypy/bandit and pytest, codegen
escalates models on failure, the planner proposes real multi-step plans
with an iterative research loop, the judge takes a median over samples,
the human-review queue is SQLite-backed with approve/reject endpoints,
and the gateway enforces API-key auth on `/intents` plus HMAC-verified
webhooks. The whole pipeline has been run end to end against a real
repo, producing a real merged commit in the scratch checkout.

Still open: `scripts/seed_eval_set.py` (calibrating the confidence
thresholds against real merged PRs) and swapping the commit-to-scratch
"auto-merge" for opening a real GitHub PR (touches only
`_auto_merge` in `services/gateway/app/pipeline.py`).

## Troubleshooting

- `password authentication failed` on retrieval at first boot — the
  pgdata volume was initialized with an old password: `docker compose
  down -v && docker compose up -d`.
- A pipeline run fails with a `502` — the gateway now logs every stage
  (`stage=... intent=...`) and the error names the failing stage; check
  `docker logs codegate-gateway-1`.
- Old `logging:` exporter in otel-collector — current config uses the
  `debug` exporter (the collector image rejects `logging`).
