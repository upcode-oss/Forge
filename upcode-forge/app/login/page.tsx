"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { InstanceLogo } from "@/components/instance-logo";
import { api, json } from "@/services/api";
import { useInstance } from "@/hooks/use-instance";

export default function Login() {
  const router = useRouter();
  const instance = useInstance();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [twoFactor, setTwoFactor] = useState(false);
  const [credentials, setCredentials] = useState<{
    username: string;
    password: string;
  }>();
  const [code, setCode] = useState("");
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
      const result = await api<{ two_factor_required?: boolean }>(
        "/auth/login",
        {
          method: "POST",
          body: json(
            twoFactor
              ? { ...credentials, two_factor_code: code }
              : Object.fromEntries(values),
          ),
        },
      );
      if (result.two_factor_required) {
        setCredentials({
          username: String(values.get("username")),
          password: String(values.get("password")),
        });
        setTwoFactor(true);
        return;
      }
      setCredentials(undefined);
      setCode("");
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
          <InstanceLogo
            instance={instance.data}
            width={220}
            height={70}
            priority
          />
          <h1>{twoFactor ? "Verify your sign-in" : "Welcome back"}</h1>
          <p>
            {twoFactor
              ? "Enter an authenticator code or an unused recovery code."
              : "Sign in to your Git workspace."}
          </p>
        </div>
        <form
          className="form-grid"
          onSubmit={submit}
          key={twoFactor ? "factor" : "password"}
        >
          {twoFactor ? (
            <Field label="Authenticator or recovery code">
              <Input
                autoFocus
                required
                autoComplete="one-time-code"
                name="two_factor_code"
                maxLength={32}
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
            </Field>
          ) : (
            <>
              <Field label="Username">
                <Input
                  name="username"
                  autoComplete="username"
                  required
                  autoFocus
                />
              </Field>
              <Field label="Password">
                <Input
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </Field>
            </>
          )}
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <Button loading={busy}>
            {twoFactor ? "Verify and sign in" : "Sign in"}
          </Button>
          {twoFactor ? (
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setTwoFactor(false);
                setCredentials(undefined);
                setCode("");
                setError("");
              }}
            >
              Back to password
            </Button>
          ) : null}
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
