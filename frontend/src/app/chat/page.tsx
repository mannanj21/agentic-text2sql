"use client";

import { FormEvent, useState } from "react";
import { apiFetch } from "@/lib/api";

type StreamEvent = { type: string; node?: string; sql?: string; answer?: string; error?: string };

export default function ChatPage() {
  const [connectionId, setConnectionId] = useState("");
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [busy, setBusy] = useState(false);
  async function submit(form: FormEvent<HTMLFormElement>) {
    form.preventDefault(); setBusy(true); setEvents([]);
    try {
      const question = String(new FormData(form.currentTarget).get("question") || "");
      const conversation = await apiFetch<{ id: string }>("/conversations", { method: "POST", body: JSON.stringify({ connection_id: connectionId }) });
      const response = await fetch(`/api/conversations/${conversation.id}/query`, { method: "POST", credentials: "include", headers: { "content-type": "application/json" }, body: JSON.stringify({ question }) });
      const reader = response.body?.getReader(); if (!reader) throw new Error("Streaming unavailable");
      const decoder = new TextDecoder(); let buffer = "";
      for (;;) { const chunk = await reader.read(); if (chunk.done) break; buffer += decoder.decode(chunk.value, { stream: true }); const lines = buffer.split("\n"); buffer = lines.pop() || ""; for (const line of lines) if (line.startsWith("data: ")) setEvents((old) => [...old, JSON.parse(line.slice(6)) as StreamEvent]); }
    } catch (error) { setEvents((old) => [...old, { type: "error", error: String(error) }]); } finally { setBusy(false); }
  }
  return <main className="mx-auto max-w-3xl p-8"><h1 className="text-3xl font-semibold">Ask your data</h1><form onSubmit={submit} className="mt-6 grid gap-3"><input required value={connectionId} onChange={(event) => setConnectionId(event.target.value)} placeholder="Connection ID" className="rounded border p-3"/><textarea required name="question" placeholder="Ask a question" className="rounded border p-3"/><button disabled={busy} className="rounded bg-black p-3 text-white">{busy ? "Working…" : "Ask"}</button></form><section className="mt-6 space-y-2">{events.map((event, index) => <p key={index} className="rounded border p-3">{event.type}: {event.node || event.answer || event.sql || event.error || "complete"}</p>)}</section></main>;
}
