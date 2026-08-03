// Embeds the Grafana agent-pipeline dashboard rather than reimplementing
// charts here — one source of truth for cost/latency/quality metrics.
export default function MetricsPage() {
  const grafanaUrl = process.env.NEXT_PUBLIC_GRAFANA_URL ?? "http://localhost:3001";

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-xl font-medium">Pipeline metrics</h1>
      <iframe
        src={`${grafanaUrl}/d/agent-pipeline?kiosk`}
        className="mt-6 h-[720px] w-full rounded-lg border border-neutral-200"
      />
    </main>
  );
}
