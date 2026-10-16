"use client";

import { FormEvent, useState } from "react";
import { ExternalLink, Link2, RefreshCw, Unplug } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { ErrorState, Loading } from "@/components/states";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";

type Connection = {
  connection_id: string;
  name: string;
  url: string;
  product: "forge" | "sprint";
  state: "pending" | "connected";
  created_at: string;
};
const endpoint = "/integrations/instance";

export function InstanceConnection({
  peerName = "Sprint",
}: {
  peerName?: string;
}) {
  const resource = useResource<Connection | null>(endpoint);
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<"both" | "local" | null>(null);
  const [checked, setChecked] = useState<"ok" | "failed" | null>(null);
  const [canRemoveLocally, setCanRemoveLocally] = useState(false);
  const [password, setPassword] = useState("");
  const connection = resource.data;

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    setChecked(null);
    try {
      await api(endpoint, { method: "POST", body: json(values) });
      notify(`${peerName} connected on both instances`);
      setChecked("ok");
      setCanRemoveLocally(false);
    } catch (reason) {
      notify((reason as Error).message, "error");
      setCanRemoveLocally(true);
    } finally {
      setPassword("");
      await resource.reload();
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    try {
      await api(`${endpoint}/test`, { method: "POST" });
      setChecked("ok");
      setCanRemoveLocally(false);
      notify("Connection verified in both directions");
      await resource.reload();
    } catch (reason) {
      setChecked("failed");
      setCanRemoveLocally(true);
      notify((reason as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      await api(`${endpoint}${confirm === "local" ? "?force=true" : ""}`, {
        method: "DELETE",
      });
      notify(
        confirm === "local"
          ? "Connection removed locally"
          : "Both instances disconnected",
      );
      setConfirm(null);
      setChecked(null);
      setCanRemoveLocally(false);
      await resource.reload();
    } catch (reason) {
      setConfirm(null);
      setCanRemoveLocally(true);
      notify((reason as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title={`${peerName} connection`}
        description={`Connect your ${peerName} instance here, or start from its settings. One setup links both instances.`}
      />
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState message={resource.error} retry={resource.reload} />
      ) : (
        <div className="form-grid">
          {connection ? (
            <>
              <div>
                <strong>{connection.name}</strong>
                <p className="muted small">
                  <a href={connection.url} target="_blank" rel="noreferrer">
                    {connection.url} <ExternalLink size={14} />
                  </a>
                </p>
                <p role="status">
                  {checked === "failed"
                    ? "Connection could not be verified"
                    : connection.state === "pending"
                      ? "Setup incomplete — retry or check the connection"
                      : checked === "ok"
                        ? "Connection verified"
                        : "Connection configured"}
                </p>
              </div>
              <div className="form-actions">
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => void test()}
                >
                  <RefreshCw />
                  Check connection
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  disabled={busy}
                  onClick={() => setConfirm("both")}
                >
                  <Unplug />
                  Disconnect
                </Button>
              </div>
              {canRemoveLocally ? (
                <div>
                  <p className="muted small">
                    If the other instance is unavailable, you can remove the
                    connection here. Remove the remaining entry in the other
                    instance separately.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busy}
                    onClick={() => setConfirm("local")}
                  >
                    Remove locally
                  </Button>
                </div>
              ) : null}
            </>
          ) : null}
          {!connection || connection.state === "pending" ? (
            <form
              className="form-grid"
              onSubmit={(event) => void connect(event)}
            >
              <Field
                label={`${peerName} public URL`}
                hint="Both public URLs must be reachable from the other server. Use HTTPS outside a trusted local network."
              >
                <Input
                  name="url"
                  type="url"
                  required
                  maxLength={500}
                  placeholder={`https://${peerName.toLowerCase()}.example.com`}
                  defaultValue={connection?.url ?? ""}
                  readOnly={Boolean(connection)}
                  disabled={busy}
                />
              </Field>
              <Field label={`${peerName} administrator username`}>
                <Input
                  name="username"
                  required
                  maxLength={254}
                  autoComplete="off"
                  disabled={busy}
                />
              </Field>
              <Field
                label={`${peerName} administrator password`}
                hint="Used once to authorize pairing. Only the separate connection key is stored, encrypted."
              >
                <Input
                  name="password"
                  type="password"
                  required
                  maxLength={256}
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  disabled={busy}
                />
              </Field>
              <div className="form-actions">
                <Button loading={busy}>
                  <Link2 />
                  {connection ? "Retry connection" : `Connect ${peerName}`}
                </Button>
              </div>
            </form>
          ) : null}
        </div>
      )}
      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!busy && !open) setConfirm(null);
        }}
        title={
          confirm === "local"
            ? "Remove connection locally?"
            : `Disconnect ${peerName}?`
        }
        description={
          confirm === "local"
            ? "The key will be revoked here. The other instance may retain its entry until you remove it there."
            : "This removes the saved connection and revokes its key on both instances."
        }
        onConfirm={() => void disconnect()}
        loading={busy}
      />
    </Card>
  );
}
