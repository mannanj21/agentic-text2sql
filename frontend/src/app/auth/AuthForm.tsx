"use client";

import { FormEvent, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      setDone(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to contact the service.");
    }
  };
  return <form onSubmit={submit} className="mx-auto flex w-full max-w-sm flex-col gap-4 p-8">
    <h1 className="text-2xl font-semibold">{mode === "login" ? "Welcome back" : "Create account"}</h1>
    <input name="email" type="email" required placeholder="Email" className="rounded border p-3" />
    <input name="password" type="password" required minLength={8} placeholder="Password" className="rounded border p-3" />
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {done ? <p>Success.</p> : <button className="rounded bg-black p-3 text-white" type="submit">{mode === "login" ? "Log in" : "Register"}</button>}
  </form>;
}
