// Mirrors shared/schemas.py — keep these two in sync by hand for now,
// or generate this file from the FastAPI OpenAPI schema later.

export type GuardrailAction = "auto_merge" | "human_review" | "reject";

export interface ReviewItem {
  intentId: string;
  repo: string;
  prompt: string;
  diff: string;
  confidence: number;
  reason: string;
  submittedAt: string;
}
