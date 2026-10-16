"use client";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { api, json } from "@/services/api";
import { useResource } from "@/hooks/use-resource";
import type { Instance } from "@/types/api";

export default function Login() {
  const router = useRouter();
  const instance = useResource<Instance>("/instance");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ completed: boolean }>("/setup/status")
      .then((s) => {
        if (!s.completed) router.replace("/setup");
      })
      .catch((e) => setError(e.message));
  }, [router]);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const values = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api("/auth/login", {
        method: "POST",
        body: json(Object.fromEntries(values)),
      });
      router.replace("/dashboard");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="centered-page">
      <Card className="auth-card">
        <div className="auth-heading">
          <Image
            src="/logo.png"
            alt="Upcode Forge"
            width={220}
            height={70}
            priority
          />
          <h1>Welcome back</h1>
          <p>Sign in to your Git workspace.</p>
        </div>
        <form className="form-grid" onSubmit={submit}>
          <Field label="Username">
            <Input name="username" autoComplete="username" required autoFocus />
          </Field>
          <Field label="Password">
            <Input
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </Field>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <Button loading={busy}>Sign in</Button>
        </form>
        <p className="muted small auth-footnote">
          {instance.data?.registration_enabled ? (
            <>
              New to Forge?{" "}
              <Link className="text-link" href="/register">
                Create an account
              </Link>
            </>
          ) : (
            "Accounts are managed by your Forge administrator."
          )}
        </p>
        <Link href="/explore/repositories" className="text-link small">
          Explore public repositories
        </Link>
      </Card>
    </main>
  );
}
