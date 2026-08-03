# Deploying codegate to Kubernetes

Full manifest set for the whole stack in one namespace (`codegate`).

## 1. Create the secret (never apply `secrets.example.yaml` as-is)

```powershell
# generate values
$env:POSTGRES_PASSWORD     = "use-secrets-token-urlsafe-32"
$env:GATEWAY_API_KEY       = "use-secrets-token-urlsafe-32"
$env:GITHUB_WEBHOOK_SECRET = "use-secrets-token-urlsafe-32"
$env:OPENROUTER_API_KEY    = "sk-or-v1-..."   # from https://openrouter.ai

kubectl create secret generic codegate-secrets --namespace codegate `
  --from-literal=POSTGRES_PASSWORD=$env:POSTGRES_PASSWORD `
  --from-literal=POSTGRES_USER=codegate `
  --from-literal=POSTGRES_DB=codegate `
  --from-literal=DATABASE_URL="postgresql://codegate:$env:POSTGRES_PASSWORD@postgres:5432/codegate" `
  --from-literal=GATEWAY_API_KEY=$env:GATEWAY_API_KEY `
  --from-literal=GITHUB_WEBHOOK_SECRET=$env:GITHUB_WEBHOOK_SECRET `
  --from-literal=OPENROUTER_API_KEY=$env:OPENROUTER_API_KEY
```

## 2. Apply everything

```powershell
kubectl apply -f infra/k8s/
```

Pulling from ghcr.io requires cluster credentials for the package (it is
private by default): create an imagePullSecret from the same token and add
it to every deployment:

```powershell
kubectl create secret docker-registry ghcr-pull --namespace codegate `
  --docker-server=ghcr.io --docker-username=grizzleyyybear --docker-password="$(gh auth token)"
# then uncomment imagePullSecrets in each infra/k8s/*-deployment.yaml
```

Order does not matter (namespace is in the set; every other object declares it).

## 3. Verify

```powershell
kubectl get pods -n codegate
kubectl port-forward -n codegate svc/gateway 8000:8000
kubectl port-forward -n codegate svc/dashboard 3000:3000
```

`POST /intents` requires `X-API-Key: <GATEWAY_API_KEY>`.

## Layout

| File | Deploys |
|---|---|
| `namespace.yaml` | `codegate` namespace |
| `secrets.example.yaml` | template only — apply via step 1 |
| `configmap.yaml` | shared non-secret env |
| `postgres-statefulset.yaml` | pgvector + headless service + initdb ConfigMap |
| `otel-collector.yaml` | OTel collector (traces in, prometheus + logs out) |
| `orchestrator/retrieval/codegen/validator/guardrail/gateway-deployment.yaml` | pipeline services + ClusterIP services |
| `dashboard-deployment.yaml` | Next.js review UI |
| `ingress.yaml` | optional — needs an ingress controller |

## Notes

- Images are `ghcr.io/grizzleyyybear/<name>:latest` — already built and
  pushed; rebuild with
  `docker build -f services/<name>/Dockerfile -t ghcr.io/grizzleyyybear/<name>:latest .`
  (dashboard: `docker build -t ghcr.io/grizzleyyybear/dashboard:latest ./dashboard`).
  A private ghcr.io package requires an imagePullSecret on the pods.
- `/work` (repos, review queue) is an `emptyDir` on gateway/codegen/validator/retrieval —
  swap for a shared PVC if you want clones to survive restarts.
- The pipeline assumes the retrieval vector schema exists — the postgres pod
  bootstraps it on first start via `codegate-initdb`.
