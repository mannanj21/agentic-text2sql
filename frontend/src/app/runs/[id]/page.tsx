"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Run = { question: string; status: string; final_sql: string | null; answer: string | null; error: string | null; steps: { seq: number; node: string; status: string; latency_ms: number | null; error: string | null }[] };

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const [run, setRun] = useState<Run | null>(null);
  useEffect(() => { void Promise.resolve().then(async () => setRun(await apiFetch<Run>(`/runs/${(await params).id}`))); }, [params]);
  if (!run) return <main className="p-8">Loading trace…</main>;
  return <main className="mx-auto max-w-3xl p-8"><h1 className="text-3xl font-semibold">Run trace</h1><p className="mt-3">{run.question}</p><p>{run.status}</p>{run.final_sql && <pre className="mt-4 overflow-auto rounded border p-3">{run.final_sql}</pre>}{run.answer && <p className="mt-4">{run.answer}</p>}{run.error && <p role="alert" className="text-red-700">{run.error}</p>}<ol className="mt-6 space-y-2">{run.steps.map((step) => <li className="rounded border p-3" key={step.seq}>{step.seq}. {step.node} · {step.status} · {step.latency_ms ?? 0}ms {step.error}</li>)}</ol></main>;
}
