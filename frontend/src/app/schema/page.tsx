"use client";

import { FormEvent, useState } from "react";
import { apiFetch } from "@/lib/api";

type Schema = { tables: { id: string; schema: string; name: string; columns: { id: string; name: string; data_type: string; is_sensitive: boolean }[] }[] };
type Term = { id: string; term: string; definition: string };

export default function SchemaPage() {
  const [connectionId, setConnectionId] = useState(""); const [schema, setSchema] = useState<Schema | null>(null); const [terms, setTerms] = useState<Term[]>([]);
  const load = async () => { setSchema(await apiFetch<Schema>(`/connections/${connectionId}/schema`)); setTerms(await apiFetch<Term[]>(`/connections/${connectionId}/glossary`)); };
  const addTerm = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); await apiFetch(`/connections/${connectionId}/glossary`, { method: "POST", body: JSON.stringify({ term: form.get("term"), definition: form.get("definition") }) }); event.currentTarget.reset(); await load(); };
  return <main className="mx-auto max-w-3xl p-8"><h1 className="text-3xl font-semibold">Schema & glossary</h1><div className="mt-4 flex gap-2"><input value={connectionId} onChange={(event) => setConnectionId(event.target.value)} placeholder="Connection ID" className="rounded border p-2"/><button onClick={() => void load()} className="rounded bg-black px-4 text-white">Load</button></div>{schema?.tables.map((table) => <section className="mt-4 rounded border p-3" key={table.id}><h2>{table.schema}.{table.name}</h2>{table.columns.map((column) => <p key={column.id}>{column.name} ({column.data_type}) {column.is_sensitive ? "sensitive" : ""}</p>)}</section>)}<form onSubmit={addTerm} className="mt-6 grid gap-2"><input name="term" required placeholder="Glossary term" className="rounded border p-2"/><input name="definition" required placeholder="Definition" className="rounded border p-2"/><button className="rounded bg-black p-2 text-white">Add glossary term</button></form><ul className="mt-4">{terms.map((term) => <li key={term.id}>{term.term}: {term.definition}</li>)}</ul></main>;
}
