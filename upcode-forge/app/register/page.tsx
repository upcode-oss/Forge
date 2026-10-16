"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Empty, ErrorState, Loading } from "@/components/states";
import { InstanceLogo } from "@/components/instance-logo";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { useInstance } from "@/hooks/use-instance";
import { api, ApiError, json } from "@/services/api";

export default function Register() {
  const router = useRouter();
  const instance = useInstance();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (form.get("password") !== form.get("confirm_password")) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api("/auth/register", {
        method: "POST",
        body: json({
          username: form.get("username"),
          display_name: form.get("display_name"),
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      router.replace("/dashboard");
    } catch (error) {
      setError((error as Error).message);
      if (error instanceof ApiError && error.status === 403) instance.reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="centered-page">
      <Card className="auth-card">
        <div className="auth-heading">
          <InstanceLogo
            instance={instance.data}
            width={220}
            height={70}
            priority
          />
          <h1>Create your account</h1>
          <p>Join {instance.data?.name || "your Forge community"}.</p>
        </div>
        {instance.loading ? (
          <Loading />
        ) : instance.error ? (
          <ErrorState message={instance.error} retry={instance.reload} />
        ) : !instance.data?.registration_enabled ? (
          <Empty
            title="Registration is closed"
            description="Account registration is currently disabled by the instance administrator."
          />
        ) : (
          <form className="form-grid" onSubmit={submit}>
            <Field
              label="Username"
              hint="Lowercase letters, numbers, underscores or hyphens; start with a letter."
            >
              <Input
                name="username"
                autoComplete="username"
                pattern="[a-z][a-z0-9_-]{0,49}"
                maxLength={50}
                required
                autoFocus
              />
            </Field>
            <Field label="Display name">
              <Input
                name="display_name"
                autoComplete="nickname"
                maxLength={100}
                required
              />
            </Field>
            <Field
              label="Email"
              hint="Your account email stays private unless you choose to publish it on your profile."
            >
              <Input name="email" type="email" autoComplete="email" required />
            </Field>
            <Field label="Password" hint="At least 12 characters.">
              <Input
                name="password"
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                required
              />
            </Field>
            <Field label="Confirm password">
              <Input
                name="confirm_password"
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                required
              />
            </Field>
            {error && (
              <p className="field-error" role="alert">
                {error}
              </p>
            )}
            <Button loading={busy}>Create account</Button>
          </form>
        )}
        <p className="muted small auth-footnote">
          Already have an account?{" "}
          <Link className="text-link" href="/login">
            Sign in
          </Link>
        </p>
        <Link className="text-link small" href="/explore/repositories">
          Explore public repositories
        </Link>
      </Card>
    </main>
  );
}
