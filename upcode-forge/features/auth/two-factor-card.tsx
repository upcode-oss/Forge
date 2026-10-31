"use client";

import { Download, ShieldCheck } from "lucide-react";
import Image from "next/image";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";

type Status = { enabled: boolean; recovery_codes_remaining: number };
type Setup = { secret: string; qr_code: string; expires_in: number };
type Action = "setup" | "disable" | "recovery-codes";

export function TwoFactorCard() {
  const resource = useResource<Status>("/auth/2fa");
  const [action, setAction] = useState<Action>();
  const [setup, setSetup] = useState<Setup>();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  function reset() {
    setAction(undefined);
    setSetup(undefined);
    setPassword("");
    setCode("");
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!action) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (action === "setup" && !setup) {
        setSetup(
          await api<Setup>("/auth/2fa/setup", {
            method: "POST",
            body: json({ password }),
          }),
        );
        setCode("");
        return;
      }
      const endpoint = action === "setup" ? "enable" : action;
      const result = await api<{ recovery_codes?: string[] }>(
        `/auth/2fa/${endpoint}`,
        {
          method: "POST",
          body: json({ password, code }),
        },
      );
      setCodes(result.recovery_codes ?? []);
      setMessage(
        action === "disable"
          ? "Two-factor authentication disabled. Other browser sessions have been signed out."
          : "Security settings updated. Other browser sessions have been signed out.",
      );
      reset();
      resource.reload();
      window.dispatchEvent(new Event("account-security-updated"));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function download() {
    const file = new Blob(
      [
        "Upcode Forge — recovery codes\n\nKeep these codes in a safe place. Each code works once.\n\n",
        codes.join("\n"),
        "\n",
      ],
      { type: "text/plain" },
    );
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = "upcode-forge-recovery-codes.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  const enabled = Boolean(codes.length || resource.data?.enabled);
  return (
    <Card>
      <CardHeader
        title="Two-factor authentication"
        description="Protect your account with an authenticator app."
        action={<ShieldCheck />}
      />
      {resource.loading && !codes.length ? (
        <p className="muted" role="status">
          Loading security settings…
        </p>
      ) : resource.error && !codes.length ? (
        <div>
          <p className="field-error" role="alert">
            {resource.error}
          </p>
          <Button type="button" variant="outline" onClick={resource.reload}>
            Retry
          </Button>
        </div>
      ) : (
        <>
          <p>
            <strong>{enabled ? "Enabled" : "Not enabled"}</strong>
            {enabled && !codes.length
              ? ` · ${resource.data?.recovery_codes_remaining ?? 0} recovery codes remaining`
              : ""}
          </p>
          {message ? (
            <p role="status" className="muted small">
              {message}
            </p>
          ) : null}
          {codes.length ? (
            <div className="form-grid">
              <p>
                <strong>Save your recovery codes now.</strong> They will only be
                shown once. Each code can replace an app code once if you lose
                access to your authenticator.
              </p>
              <div className="form-grid two">
                {codes.map((value) => (
                  <code className="mono" key={value}>
                    {value}
                  </code>
                ))}
              </div>
              <div className="form-actions">
                <Button type="button" variant="outline" onClick={download}>
                  <Download />
                  Download codes
                </Button>
                <Button type="button" onClick={() => setCodes([])}>
                  I saved these codes
                </Button>
              </div>
            </div>
          ) : action ? (
            <form className="form-grid" onSubmit={submit}>
              {setup ? (
                <>
                  <p>
                    Scan this QR code with your authenticator app. Confirm with
                    its six-digit code within ten minutes.
                  </p>
                  <Image
                    src={setup.qr_code}
                    alt="Scan to add Upcode Forge to your authenticator"
                    width={220}
                    height={220}
                    unoptimized
                    style={{
                      background: "white",
                      maxWidth: "100%",
                      height: "auto",
                    }}
                  />
                  <Field
                    label="Manual setup key"
                    hint="If scanning is unavailable, enter this key in your authenticator."
                  >
                    <Input
                      readOnly
                      value={setup.secret}
                      className="mono"
                      onFocus={(event) => event.currentTarget.select()}
                    />
                  </Field>
                </>
              ) : null}
              <Field label="Current password">
                <Input
                  type="password"
                  autoComplete="current-password"
                  required
                  maxLength={256}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  disabled={busy}
                />
              </Field>
              {setup || action !== "setup" ? (
                <Field
                  label={
                    setup
                      ? "Authenticator code"
                      : "Authenticator or recovery code"
                  }
                  hint={
                    setup
                      ? "Enter the current six-digit code."
                      : "Codes can only be used once. Wait for the next app code if needed."
                  }
                >
                  <Input
                    autoFocus
                    required
                    autoComplete="one-time-code"
                    inputMode={setup ? "numeric" : "text"}
                    maxLength={32}
                    pattern={setup ? "[0-9]{6}" : undefined}
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    disabled={busy}
                  />
                </Field>
              ) : (
                <p className="muted small">
                  Use a TOTP-compatible authenticator app. Two-factor
                  authentication starts after you confirm your first app code.
                </p>
              )}
              {action === "recovery-codes" ? (
                <p className="muted small">
                  Generating new recovery codes invalidates all previous
                  recovery codes.
                </p>
              ) : null}
              {action === "disable" ? (
                <p className="muted small">
                  Your next sign-in will require only your password.
                </p>
              ) : null}
              {error ? (
                <p className="field-error" role="alert">
                  {error}
                </p>
              ) : null}
              <div className="form-actions">
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={reset}
                >
                  Cancel
                </Button>
                <Button
                  loading={busy}
                  variant={action === "disable" ? "destructive" : "default"}
                >
                  {action === "setup"
                    ? setup
                      ? "Enable two-factor authentication"
                      : "Set up authenticator"
                    : action === "disable"
                      ? "Disable two-factor authentication"
                      : "Generate new recovery codes"}
                </Button>
              </div>
            </form>
          ) : (
            <div className="form-actions">
              {enabled ? (
                <>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setAction("recovery-codes");
                      setMessage("");
                    }}
                  >
                    Replace recovery codes
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setAction("disable");
                      setMessage("");
                    }}
                  >
                    Disable two-factor authentication
                  </Button>
                </>
              ) : (
                <Button
                  type="button"
                  onClick={() => {
                    setAction("setup");
                    setMessage("");
                  }}
                >
                  Enable two-factor authentication
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </Card>
  );
}
