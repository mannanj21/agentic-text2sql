"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type Connection = { id: string; name: string; host: string; database: string; status: string };

export default function Home() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [error, setError] = useState("");
  const load = async () => { try { setConnections(await apiFetch<Connection[]>("/connections")); } catch { setError("Log in to manage connections."); } };
  useEffect(() => { void Promise.resolve().then(load); }, []);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setError(""); const form = new FormData(event.currentTarget);
    try { await apiFetch("/connections", { method: "POST", body: JSON.stringify({ name: form.get("name"), host: form.get("host"), database: form.get("database"), username: form.get("username"), password: form.get("password"), schemas: ["public"] }) }); event.currentTarget.reset(); await load(); } catch { setError("Connection could not be created. Check the host and readonly role."); }
  };
  return <main className="mx-auto w-full max-w-3xl p-8"><h1 className="text-3xl font-semibold">Connections</h1>{error && <p role="alert" className="mt-3 text-red-700">{error}</p>}<form onSubmit={submit} className="mt-6 grid gap-3 rounded border p-4"><input name="name" required placeholder="Name" className="rounded border p-2"/><input name="host" required placeholder="Host" className="rounded border p-2"/><input name="database" required placeholder="Database" className="rounded border p-2"/><input name="username" required placeholder="Readonly username" className="rounded border p-2"/><input name="password" required type="password" placeholder="Password" className="rounded border p-2"/><button className="rounded bg-black p-2 text-white">Add connection</button></form><ul className="mt-6 space-y-2">{connections.map((connection) => <li className="rounded border p-3" key={connection.id}>{connection.name} · {connection.host}/{connection.database} · {connection.status}</li>)}</ul></main>;
}
