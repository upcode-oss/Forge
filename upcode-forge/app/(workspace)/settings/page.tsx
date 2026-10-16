"use client";
import { FormEvent, useState } from "react";
import { Mail, Save } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { ErrorState, Loading } from "@/components/states";
import { useAuth } from "@/features/auth/auth-context";
import { InstanceConnection } from "@/features/integrations/instance-connection";
import { InstanceLogoUploader } from "@/features/settings/instance-logo-uploader";
import { instanceUpdated, useInstance } from "@/hooks/use-instance";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";
import type { SMTP } from "@/types/api";

export default function Settings() {
  const me = useAuth();
  const instance = useInstance(me.is_admin);
  const smtp = useResource<SMTP>(me.is_admin ? "/instance/smtp" : null);
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>, path: string) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    try {
      await api(path, {
        method: "PUT",
        body: json(
          path.endsWith("smtp")
            ? {
                ...values,
                port: Number(values.port),
                from_address: values.from_address || null,
              }
            : {
                ...values,
                registration_enabled: values.registration_enabled === "on",
              },
        ),
      });
      if (path.endsWith("smtp")) smtp.reload();
      else instanceUpdated();
      notify("Settings saved");
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function test() {
    setBusy(true);
    try {
      await api("/instance/smtp/test", { method: "POST" });
      notify("Test email sent to your address");
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  if (!me.is_admin)
    return <ErrorState message="Administrator access required" />;
  return (
    <>
      <PageHeader
        title="Instance & System"
        description="Configure your instance, logo, Sprint connection, Git defaults, and outgoing email."
      />
      <div className="content-grid">
        <InstanceConnection />
        <Card>
          <CardHeader
            title="Instance"
            description="The public URL is used for clone links and browser request validation."
          />
          {instance.loading ? (
            <Loading />
          ) : instance.error ? (
            <ErrorState message={instance.error} retry={instance.reload} />
          ) : (
            instance.data && (
              <form
                className="form-grid"
                onSubmit={(e) => void save(e, "/instance")}
                key={JSON.stringify(instance.data)}
              >
                <Field label="Instance name">
                  <Input
                    name="name"
                    required
                    maxLength={100}
                    defaultValue={instance.data.name}
                  />
                </Field>
                <Field label="Public URL">
                  <Input
                    name="public_url"
                    type="url"
                    required
                    defaultValue={instance.data.public_url}
                  />
                </Field>
                <Field label="Default branch for new repositories">
                  <Input
                    name="default_branch"
                    required
                    maxLength={100}
                    defaultValue={instance.data.default_branch}
                  />
                </Field>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    name="registration_enabled"
                    defaultChecked={instance.data.registration_enabled}
                    disabled={busy}
                  />
                  Allow public registration
                </label>
                <p className="muted small">
                  Visitors can create their own accounts when enabled. New
                  accounts have no administrator privileges. Disabling
                  registration keeps existing accounts active.
                </p>
                <div className="form-actions">
                  <Button loading={busy}>
                    <Save />
                    Save changes
                  </Button>
                </div>
              </form>
            )
          )}
          <div className="divider" />
          <p className="muted small">
            Forge v0.1.0 · Git over HTTP(S) · FastAPI · SQLAlchemy · Next.js
          </p>
          <p className="muted small">
            Database credentials and repositories are persisted in the
            forge_data volume. Database changes require a backup and migration;
            the setup wizard stays locked.
          </p>
        </Card>
        <Card>
          <CardHeader
            title="Branding"
            description="Use your own logo throughout this Forge instance."
          />
          {instance.loading ? (
            <Loading />
          ) : instance.error ? (
            <ErrorState message={instance.error} retry={instance.reload} />
          ) : instance.data ? (
            <InstanceLogoUploader instance={instance.data} />
          ) : null}
        </Card>
        <Card>
          <CardHeader
            title="SMTP"
            description="Optional outgoing email. Save your configuration, then send a test email."
          />
          {smtp.loading ? (
            <Loading />
          ) : smtp.error ? (
            <ErrorState message={smtp.error} retry={smtp.reload} />
          ) : (
            smtp.data && (
              <form
                className="form-grid"
                key={JSON.stringify(smtp.data)}
                onSubmit={(e) => void save(e, "/instance/smtp")}
              >
                <div className="form-grid two">
                  <Field label="SMTP host" hint="Leave blank to disable.">
                    <Input
                      name="host"
                      defaultValue={smtp.data.host}
                      maxLength={254}
                    />
                  </Field>
                  <Field label="Port">
                    <Input
                      name="port"
                      type="number"
                      min={1}
                      max={65535}
                      defaultValue={smtp.data.port}
                      required
                    />
                  </Field>
                </div>
                <Field label="Encryption">
                  <Select name="encryption" defaultValue={smtp.data.encryption}>
                    <option value="starttls">STARTTLS</option>
                    <option value="tls">TLS</option>
                  </Select>
                </Field>
                <Field label="Username">
                  <Input
                    name="username"
                    defaultValue={smtp.data.username}
                    autoComplete="off"
                  />
                </Field>
                <Field
                  label="Password"
                  hint={
                    smtp.data.has_password
                      ? "A password is saved. Leave blank to keep it."
                      : "Stored encrypted."
                  }
                >
                  <Input
                    name="password"
                    type="password"
                    autoComplete="new-password"
                  />
                </Field>
                <Field label="Sender email">
                  <Input
                    name="from_address"
                    type="email"
                    defaultValue={smtp.data.from_address ?? ""}
                  />
                </Field>
                <div className="form-actions">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busy || !smtp.data.host}
                    onClick={() => void test()}
                  >
                    <Mail />
                    Send test
                  </Button>
                  <Button loading={busy}>
                    <Save />
                    Save SMTP
                  </Button>
                </div>
              </form>
            )
          )}
        </Card>
      </div>
    </>
  );
}
