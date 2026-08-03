const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

export async function fetchReviewQueue() {
  const res = await fetch(`${GATEWAY_URL}/reviews`, { cache: "no-store" });
  if (!res.ok) throw new Error("failed to load review queue");
  return res.json();
}

export async function submitReviewDecision(intentId: string, approve: boolean) {
  return fetch(`${GATEWAY_URL}/reviews/${intentId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approve }),
  });
}
