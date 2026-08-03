"""Gateway — the single entry point. Receives an intent (or a GitHub
webhook), and walks it through every other service in order. Also the
service the dashboard talks to for the human-review queue.
"""
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from shared.otel_setup import setup_otel
from shared.schemas import IntentRequest

from . import review_queue
from .auth import require_api_key
from .pipeline import _auto_merge, run_pipeline
from .webhooks import router as webhook_router

setup_otel("codegate-gateway")
app = FastAPI(title="Codegate Gateway")
app.include_router(webhook_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/intents", dependencies=[Depends(require_api_key)])
async def submit_intent(intent: IntentRequest):
    return await run_pipeline(intent)


class ReviewDecision(BaseModel):
    approve: bool


@app.get("/reviews")
def list_reviews():
    return review_queue.list_pending()


@app.post("/reviews/{intent_id}", dependencies=[Depends(require_api_key)])
def decide_review(intent_id: str, decision: ReviewDecision):
    item = review_queue.decide(intent_id, decision.approve)
    if item is None:
        raise HTTPException(status_code=404, detail="review not found")
    outcome: dict = {"status": item["status"]}
    if decision.approve:
        outcome["merge"] = _auto_merge(
            {"intent_id": item["intent_id"], "repo": item["repo"],
             "diff": item["diff"], "model_used": "human-approved"}
        )
    return outcome
