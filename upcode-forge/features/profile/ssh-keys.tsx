"use client";

import { FormEvent, useState } from "react";
import { KeyRound, Plus, Trash2 } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { ErrorState, Loading } from "@/components/states";
import { useToast } from "@/components/ui/toast";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";
import { formatDate } from "@/lib/utils";
import type { SSHKey, SSHStatus } from "@/types/api";

export function SSHKeysCard() {
  const keys = useResource<SSHKey[]>("/ssh-keys");
  const status = useResource<SSHStatus>("/ssh");
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [removing, setRemoving] = useState<SSHKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    setError("");
    try {
      await api("/ssh-keys", { method: "POST", body: json(values) });
      setOpen(false);
      keys.reload();
      notify("SSH key added");
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api(`/ssh-keys/${removing.id}`, { method: "DELETE" });
      setRemoving(null);
      keys.reload();
      notify("SSH key removed");
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="wide">
      <CardHeader
        title="SSH keys"
        description="Clone, fetch and push using your SSH key. Repository permissions still apply."
        action={
          <Button
            onClick={() => {
              setError("");
              setOpen(true);
            }}
          >
            <Plus /> Add SSH key
          </Button>
        }
      />
      {status.error && (
        <ErrorState message={status.error} retry={status.reload} />
      )}
      {status.data &&
        (status.data.enabled ? (
          <div className="ssh-connection-info">
            <p className="muted small">Test your connection:</p>
            <code>
              ssh -T -p {status.data.port} git@{status.data.host}
            </code>
            {status.data.host_fingerprint && (
              <p className="muted small">
                Server host key:{" "}
                <code className="ssh-fingerprint">
                  {status.data.host_fingerprint}
                </code>
              </p>
            )}
          </div>
        ) : (
          <p className="muted small">
            SSH transport is disabled on this instance. You can save keys now;
            an administrator must enable SSH before connecting.
          </p>
        ))}
      {keys.loading ? (
        <Loading />
      ) : keys.error ? (
        <ErrorState message={keys.error} retry={keys.reload} />
      ) : keys.data?.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name / fingerprint</th>
                <th>Scope</th>
                <th>Added</th>
                <th>Last used</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {keys.data.map((key) => (
                <tr key={key.id}>
                  <td>
                    <div className="ssh-key-name">
                      <KeyRound /> {key.name}
                    </div>
                    <code className="ssh-fingerprint muted small">
                      {key.fingerprint}
                    </code>
                  </td>
                  <td>
                    <span className="badge">
                      {key.scope === "read" ? "Read only" : "Read & write"}
                    </span>
                  </td>
                  <td>{formatDate(key.created_at)}</td>
                  <td>
                    {key.last_used_at
                      ? formatDate(key.last_used_at, true)
                      : "Never"}
                  </td>
                  <td>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove SSH key ${key.name}`}
                      onClick={() => setRemoving(key)}
                    >
                      <Trash2 />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">
          No SSH keys yet. Add the public key from your computer to use SSH
          clone URLs.
        </p>
      )}
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value);
        }}
        title="Add an SSH key"
        description="Your private key stays on your computer."
      >
        <form className="form-grid" onSubmit={add}>
          <Field label="Key name">
            <Input
              name="name"
              required
              maxLength={100}
              placeholder="Work laptop"
              autoFocus
              disabled={busy}
            />
          </Field>
          <Field
            label="Public key"
            hint="Paste one line from your .pub file. Ed25519, ECDSA or RSA (2048+ bits)."
          >
            <Textarea
              name="public_key"
              required
              maxLength={16384}
              className="mono"
              placeholder="ssh-ed25519 AAAA… you@laptop"
              spellCheck={false}
              disabled={busy}
            />
          </Field>
          <Field label="Scope">
            <Select name="scope" defaultValue="write" disabled={busy}>
              <option value="write">Read and write</option>
              <option value="read">Read only</option>
            </Select>
          </Field>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="form-actions">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button loading={busy}>Add SSH key</Button>
          </div>
        </form>
      </Dialog>
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(value) => {
          if (!value && !busy) setRemoving(null);
        }}
        title="Remove SSH key?"
        description={`New Git commands using “${removing?.name}” will lose SSH access immediately.`}
        loading={busy}
        onConfirm={() => void remove()}
      />
    </Card>
  );
}
