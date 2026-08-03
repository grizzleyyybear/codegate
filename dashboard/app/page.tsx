// Review queue — every intent the guardrail routed to human_review lands
// here. This is the "governance, escalation, human-AI collaboration"
// bullet's UI half.
import Link from "next/link";
import { fetchReviewQueue } from "../lib/api";

export default async function QueuePage() {
  const items = await fetchReviewQueue().catch(() => []);

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-xl font-medium">Review queue</h1>
      <p className="mt-1 text-sm text-neutral-500">
        Patches the guardrail flagged for human review before merge.
      </p>

      <ul className="mt-6 divide-y divide-neutral-200">
        {items.length === 0 && (
          <li className="py-6 text-sm text-neutral-500">Nothing waiting on review.</li>
        )}
        {items.map((item: any) => (
          <li key={item.intentId} className="flex items-center justify-between py-4">
            <div>
              <p className="text-sm font-medium">{item.prompt}</p>
              <p className="text-xs text-neutral-500">
                {item.repo} · confidence {item.confidence.toFixed(2)} · {item.reason}
              </p>
            </div>
            <Link
              href={`/review/${item.intentId}`}
              className="text-sm text-blue-600 hover:underline"
            >
              Review
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
