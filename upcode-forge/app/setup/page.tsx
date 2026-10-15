"use client";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Database,
  GitBranch,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/form";
import { Loading } from "@/components/states";
import { api, json } from "@/services/api";

const steps = [
  { label: "Instance", icon: SlidersHorizontal },
  { label: "Database", icon: Database },
  { label: "Administrator", icon: ShieldCheck },
  { label: "Review & Install", icon: GitBranch },
];
export default function SetupPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [values, setValues] = useState({
    name: "Upcode Forge",
    public_url: "http://localhost:3000",
    default_branch: "main",
    setup_token: "",
    database_engine: "sqlite",
    database_host: "postgres",
    database_port: 5432,
    database_name: "forge",
    database_user: "forge",
    database_password: "",
    admin: { username: "", display_name: "", email: "", password: "" },
  });
  useEffect(() => {
    setValues((v) => ({ ...v, public_url: window.location.origin }));
    api<{ completed: boolean }>("/setup/status")
      .then((s) => {
        if (s.completed) router.replace("/login");
        else setReady(true);
      })
      .catch((e) => {
        setError(e.message);
        setReady(true);
      });
  }, [router]);
  function field(key: keyof typeof values, value: string | number) {
    setValues((v) => ({ ...v, [key]: value }));
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (step < 3) {
      setStep((s) => s + 1);
      return;
    }
    setBusy(true);
    try {
      await api("/setup", { method: "POST", body: json(values) });
      router.replace("/login");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!ready) return <Loading />;
  return (
    <main className="centered-page">
      <div className="setup-shell">
        <div className="auth-heading">
          <Image
            src="/logo.png"
            alt="Upcode Forge"
            width={240}
            height={76}
            priority
          />
          <h1>Your code starts here</h1>
          <p>Set up your self-hosted Git workspace.</p>
        </div>
        <div className="setup-progress">
          {steps.map((item, i) => (
            <div
              key={item.label}
              className={`setup-step ${i === step ? "active" : i < step ? "done" : ""}`}
            >
              {i < step ? <Check /> : <item.icon />} {i + 1}.{" "}
              <span>{item.label}</span>
            </div>
          ))}
        </div>
        <Card className="setup-card">
          <form onSubmit={submit}>
            {step === 0 && (
              <>
                <CardHeader
                  title="Configure your instance"
                  description="Give your workspace a name and public address."
                />
                <div className="form-grid">
                  <Field label="Instance name">
                    <Input
                      value={values.name}
                      onChange={(e) => field("name", e.target.value)}
                      maxLength={100}
                      required
                    />
                  </Field>
                  <Field
                    label="Public URL"
                    hint="The address used for clone URLs. Set FORGE_PUBLIC_URL in .env to this origin when deploying remotely."
                  >
                    <Input
                      type="url"
                      value={values.public_url}
                      onChange={(e) => field("public_url", e.target.value)}
                      required
                    />
                  </Field>
                  <Field label="Default branch">
                    <Input
                      value={values.default_branch}
                      onChange={(e) => field("default_branch", e.target.value)}
                      required
                      maxLength={100}
                    />
                  </Field>
                  <Field
                    label="Setup token"
                    hint="Use FORGE_SETUP_TOKEN from your .env file to authorize this first installation."
                  >
                    <Input
                      type="password"
                      value={values.setup_token}
                      onChange={(e) => field("setup_token", e.target.value)}
                      required
                      minLength={32}
                      autoComplete="off"
                    />
                  </Field>
                </div>
              </>
            )}
            {step === 1 && (
              <>
                <CardHeader
                  title="Choose your database"
                  description="Application data and Git repositories are persisted in Docker volumes."
                />
                <div className="form-grid">
                  <Field label="Database engine">
                    <Select
                      value={values.database_engine}
                      onChange={(e) => {
                        const engine = e.target.value;
                        setValues((v) => ({
                          ...v,
                          database_engine: engine,
                          database_host:
                            engine === "mysql" ? "mariadb" : "postgres",
                          database_port: engine === "mysql" ? 3306 : 5432,
                        }));
                      }}
                    >
                      <option value="sqlite">SQLite — built in</option>
                      <option value="postgresql">PostgreSQL</option>
                      <option value="mysql">MariaDB / MySQL</option>
                    </Select>
                  </Field>
                  {values.database_engine === "sqlite" ? (
                    <div className="notice">
                      <Database />
                      <p>
                        SQLite needs no additional service. The database is
                        stored at <code>/data/forge.db</code> alongside your
                        encrypted installation configuration.
                      </p>
                    </div>
                  ) : (
                    <>
                      <p className="muted small">
                        Start the matching Compose profile first and use the
                        same credentials as in .env. External database servers
                        are also supported.
                      </p>
                      <div className="form-grid two">
                        <Field label="Host">
                          <Input
                            value={values.database_host}
                            onChange={(e) =>
                              field("database_host", e.target.value)
                            }
                            required
                          />
                        </Field>
                        <Field label="Port">
                          <Input
                            type="number"
                            min={1}
                            max={65535}
                            value={values.database_port}
                            onChange={(e) =>
                              field("database_port", Number(e.target.value))
                            }
                            required
                          />
                        </Field>
                        <Field label="Database">
                          <Input
                            value={values.database_name}
                            onChange={(e) =>
                              field("database_name", e.target.value)
                            }
                            required
                          />
                        </Field>
                        <Field label="Username">
                          <Input
                            value={values.database_user}
                            onChange={(e) =>
                              field("database_user", e.target.value)
                            }
                            required
                          />
                        </Field>
                      </div>
                      <Field label="Database password">
                        <Input
                          type="password"
                          value={values.database_password}
                          onChange={(e) =>
                            field("database_password", e.target.value)
                          }
                          required
                          autoComplete="new-password"
                        />
                      </Field>
                    </>
                  )}
                </div>
              </>
            )}
            {step === 2 && (
              <>
                <CardHeader
                  title="Create your administrator"
                  description="This account manages users, instance settings, and repositories."
                />
                <div className="form-grid">
                  {(
                    [
                      ["display_name", "Display name", "text"],
                      ["username", "Username", "text"],
                      ["email", "Email address", "email"],
                      ["password", "Password", "password"],
                    ] as const
                  ).map(([key, label, type]) => (
                    <Field
                      key={key}
                      label={label}
                      hint={
                        key === "password"
                          ? "Use at least 12 characters."
                          : key === "username"
                            ? "Lowercase letters, numbers, underscores and hyphens. Start with a letter."
                            : undefined
                      }
                    >
                      <Input
                        type={type}
                        value={values.admin[key]}
                        onChange={(e) =>
                          setValues((v) => ({
                            ...v,
                            admin: { ...v.admin, [key]: e.target.value },
                          }))
                        }
                        required
                        minLength={key === "password" ? 12 : 1}
                        maxLength={
                          key === "password"
                            ? 256
                            : key === "username"
                              ? 50
                              : 100
                        }
                        pattern={
                          key === "username" ? "[a-z][a-z0-9_-]*" : undefined
                        }
                        autoComplete={
                          key === "password" ? "new-password" : undefined
                        }
                      />
                    </Field>
                  ))}
                </div>
              </>
            )}
            {step === 3 && (
              <>
                <CardHeader
                  title="Ready to forge"
                  description="Review your configuration before creating the installation."
                />
                <div className="review-list">
                  {[
                    ["Instance", values.name],
                    ["Public URL", values.public_url],
                    ["Default branch", values.default_branch],
                    [
                      "Database",
                      values.database_engine === "sqlite"
                        ? "SQLite (persistent volume)"
                        : `${values.database_engine} · ${values.database_host}:${values.database_port}/${values.database_name}`,
                    ],
                    [
                      "Administrator",
                      `${values.admin.display_name} (@${values.admin.username})`,
                    ],
                    ["Email", values.admin.email],
                  ].map(([key, value]) => (
                    <div className="split" key={key}>
                      <span className="muted">{key}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
                <div className="notice">
                  <ShieldCheck />
                  <p>
                    The setup locks after installation. You can configure
                    optional SMTP and test email delivery under Organization &
                    System.
                  </p>
                </div>
              </>
            )}
            {error && (
              <p role="alert" className="field-error">
                {error}
              </p>
            )}
            <div className="form-actions">
              {step > 0 && (
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setStep((s) => s - 1);
                    setError("");
                  }}
                >
                  <ArrowLeft />
                  Back
                </Button>
              )}
              <Button loading={busy}>
                {step === 3 ? (
                  <>
                    <Check />
                    Install Forge
                  </>
                ) : (
                  <>
                    Continue
                    <ArrowRight />
                  </>
                )}
              </Button>
            </div>
          </form>
        </Card>
        <p className="muted small auth-footnote">
          Upcode Forge · Self-hosted. Open source. Yours.
        </p>
      </div>
    </main>
  );
}
