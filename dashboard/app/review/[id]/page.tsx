// Diff + reasoning trace for one queued patch, with approve/reject.
import { fetchReviewQueue, submitReviewDecision } from "../../../lib/api";

export default async function ReviewDetailPage({ params }: { params: { id: string } }) {
  const items = await fetchReviewQueue().catch(() => []);
  const item = items.find((i: any) => i.intentId === params.id);

  if (!item) {
    return <main className="mx-auto max-w-3xl px-6 py-10">Not found.</main>;
  }

  async function decide(approve: boolean) {
    "use server";
    await submitReviewDecision(params.id, approve);
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-lg font-medium">{item.prompt}</h1>
      <p className="mt-1 text-xs text-neutral-500">
        {item.repo} · confidence {item.confidence.toFixed(2)} · flagged: {item.reason}
      </p>

      <pre className="mt-6 overflow-x-auto rounded-lg bg-neutral-950 p-4 text-xs text-neutral-100">
        {item.diff}
      </pre>

      <div className="mt-6 flex gap-3">
        <form action={decide.bind(null, true)}>
          <button className="rounded-md bg-neutral-900 px-4 py-2 text-sm text-white">
            Approve and merge
          </button>
        </form>
        <form action={decide.bind(null, false)}>
          <button className="rounded-md border border-neutral-300 px-4 py-2 text-sm">
            Reject
          </button>
        </form>
      </div>
    </main>
  );
}
