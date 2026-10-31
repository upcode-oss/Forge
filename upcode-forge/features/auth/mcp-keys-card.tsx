"use client";

import { Copy, KeyRound, Plus, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";

type KeyRecord = {
  id: string;
  name: string;
  scopes: string[];
  status: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};
type KeyList = {
  keys: KeyRecord[];
  permissions: { scope: string; description: string }[];
  requires_two_factor: boolean;
};
const endpoint = "/auth/mcp-keys";

function date(value: string | null) {
  return value ? new Date(value).toLocaleDateString("en-US") : "Never";
}

export function MCPKeysCard() {
  const status = useResource<{ enabled: boolean }>("/mcp-status");
  const reloadStatus = status.reload;
  useEffect(() => {
    const reload = () => void reloadStatus();
    window.addEventListener("mcp-settings-updated", reload);
    return () => window.removeEventListener("mcp-settings-updated", reload);
  }, [reloadStatus]);
  if (!status.data?.enabled) return null;
  return <EnabledMCPKeysCard />;
}

function EnabledMCPKeysCard() {
  const resource = useResource<KeyList>(endpoint);
  const reloadKeys = resource.reload;
  useEffect(() => {
    const reload = () => void reloadKeys();
    window.addEventListener("account-security-updated", reload);
    return () => window.removeEventListener("account-security-updated", reload);
  }, [reloadKeys]);
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [days, setDays] = useState("90");
  const [scopes, setScopes] = useState<string[]>([]);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [raw, setRaw] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revoking, setRevoking] = useState<KeyRecord>();

  function begin() {
    setName("");
    setDays("90");
    setPassword("");
    setCode("");
    setRaw("");
    setError("");
    setScopes(
      resource.data?.permissions
        .filter(
          (permission) =>
            permission.scope.endsWith(".read") ||
            permission.scope.endsWith(".view"),
        )
        .map((permission) => permission.scope) ?? ["profile.read"],
    );
    setUrl(new URL("/api/v1/mcp", window.location.origin).href);
    setOpen(true);
  }

  function close(value: boolean) {
    if (busy) return;
    setOpen(value);
    if (!value) {
      setPassword("");
      setCode("");
      setRaw("");
      setError("");
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ key: string }>(endpoint, {
        method: "POST",
        body: json({
          name,
          scopes,
          expires_in_days: Number(days),
          password,
          ...(resource.data?.requires_two_factor
            ? { two_factor_code: code }
            : {}),
        }),
      });
      setRaw(result.key);
      setPassword("");
      setCode("");
      resource.reload();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!revoking) return;
    setBusy(true);
    try {
      await api(endpoint + "/" + revoking.id, { method: "DELETE" });
      setRevoking(undefined);
      resource.reload();
      notify("MCP key revoked");
    } catch (reason) {
      notify((reason as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      notify("Copied");
    } catch {
      notify("Select and copy the value manually.", "error");
    }
  }

  return (
    <>
      <Card className="wide">
        <CardHeader
          title="MCP access keys"
          description="Connect an MCP client using a personal key limited to your own permissions and accessible projects."
          action={
            <Button
              type="button"
              onClick={begin}
              disabled={resource.loading || !resource.data}
            >
              <Plus />
              Generate MCP key
            </Button>
          }
        />
        <p className="muted small">
          Every request checks your current permissions and project access.
          Losing a role or membership removes that access from your keys
          immediately. Password changes and enabling or disabling 2FA invalidate
          existing keys.
        </p>
        {resource.loading ? (
          <p role="status" className="muted">
            Loading MCP keys…
          </p>
        ) : resource.error ? (
          <div>
            <p role="alert" className="field-error">
              {resource.error}
            </p>
            <Button type="button" variant="outline" onClick={resource.reload}>
              Retry
            </Button>
          </div>
        ) : resource.data?.keys.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Permissions</th>
                  <th>Status</th>
                  <th>Expires</th>
                  <th>Last used</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {resource.data.keys.map((key) => (
                  <tr key={key.id}>
                    <td>
                      <KeyRound /> {key.name}
                    </td>
                    <td>
                      <span
                        className="muted small"
                        title={key.scopes.join(", ")}
                      >
                        {key.scopes.length} permissions
                      </span>
                    </td>
                    <td>{key.status.replaceAll("_", " ")}</td>
                    <td>{date(key.expires_at)}</td>
                    <td>{date(key.last_used_at)}</td>
                    <td>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        disabled={Boolean(key.revoked_at)}
                        aria-label={`Revoke MCP key ${key.name}`}
                        onClick={() => setRevoking(key)}
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
            No MCP keys yet. Generate a key to connect your client.
          </p>
        )}
      </Card>
      <Dialog
        open={open}
        onOpenChange={close}
        title={raw ? "Your new MCP key" : "Generate MCP key"}
        description={
          raw
            ? "Save this key now. It will only be shown once."
            : "Choose permissions from your own account and confirm your identity."
        }
      >
        {raw ? (
          <div className="form-grid">
            <Field label="MCP key">
              <Input
                readOnly
                value={raw}
                autoComplete="off"
                className="mono"
                onFocus={(event) => event.currentTarget.select()}
              />
            </Field>
            <Button
              type="button"
              variant="outline"
              onClick={() => void copy(raw)}
            >
              <Copy />
              Copy key
            </Button>
            <Field label="MCP endpoint">
              <Input
                readOnly
                value={url}
                className="mono"
                onFocus={(event) => event.currentTarget.select()}
              />
            </Field>
            <p className="muted small">
              Use Streamable HTTP and send the key in the Authorization header
              as Bearer followed by your key. Store the key in the MCP client
              secret settings.
            </p>
            <div className="form-actions">
              <Button type="button" onClick={() => close(false)}>
                I saved this key
              </Button>
            </div>
          </div>
        ) : (
          <form className="form-grid" onSubmit={create}>
            <Field label="Key name">
              <Input
                required
                autoFocus
                maxLength={100}
                value={name}
                onChange={(event) => setName(event.target.value)}
                disabled={busy}
                placeholder="My MCP client"
              />
            </Field>
            <Field label="Expiration">
              <Select
                value={days}
                onChange={(event) => setDays(event.target.value)}
                disabled={busy}
              >
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="365">1 year</option>
              </Select>
            </Field>
            <fieldset
              disabled={busy}
              className="form-grid"
              style={{ border: 0, padding: 0, minWidth: 0 }}
            >
              <legend className="field-label">Key permissions</legend>
              <p className="muted small">
                Only permissions you currently have are available. Write and
                delete permissions must be selected explicitly.
              </p>
              {resource.data?.permissions.map((permission) => (
                <label className="checkbox-field" key={permission.scope}>
                  <input
                    type="checkbox"
                    checked={scopes.includes(permission.scope)}
                    onChange={(event) =>
                      setScopes((current) =>
                        event.target.checked
                          ? [...current, permission.scope]
                          : current.filter(
                              (value) => value !== permission.scope,
                            ),
                      )
                    }
                  />
                  <span>{permission.description}</span>
                </label>
              ))}
            </fieldset>
            <Field label="Current password">
              <Input
                required
                type="password"
                autoComplete="current-password"
                maxLength={256}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                disabled={busy}
              />
            </Field>
            {resource.data?.requires_two_factor ? (
              <Field label="Authenticator or recovery code">
                <Input
                  required
                  autoComplete="one-time-code"
                  maxLength={32}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  disabled={busy}
                />
              </Field>
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
                onClick={() => close(false)}
              >
                Cancel
              </Button>
              <Button loading={busy} disabled={!scopes.length}>
                Generate key
              </Button>
            </div>
          </form>
        )}
      </Dialog>
      <ConfirmDialog
        open={Boolean(revoking)}
        onOpenChange={(value) => {
          if (!value && !busy) setRevoking(undefined);
        }}
        title="Revoke MCP key?"
        description={`Clients using “${revoking?.name}” will lose access immediately.`}
        loading={busy}
        onConfirm={() => void revoke()}
      />
    </>
  );
}
