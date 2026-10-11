"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Item = { run_id: string; question: string; status: string };

export default function HistoryPage() {
  const [items, setItems] = useState<Item[]>([]);
  useEffect(() => { void Promise.resolve().then(() => apiFetch<Item[]>("/history").then(setItems)); }, []);
  return <main className="mx-auto max-w-3xl p-8"><h1 className="text-3xl font-semibold">History</h1><ul className="mt-6 space-y-2">{items.map((item) => <li className="rounded border p-3" key={item.run_id}><Link href={`/runs/${item.run_id}`}>{item.question}</Link> · {item.status}</li>)}</ul></main>;
}
