"use client";

import { Save, Settings2 } from "lucide-react";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";

export function MCPSettingsCard() {
  const resource = useResource<{ enabled: boolean }>("/mcp-status");
  const { notify } = useToast();
  const [selection, setSelection] = useState<boolean>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const enabled = selection ?? resource.data?.enabled ?? false;

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/settings/mcp", { method: "PUT", body: json({ enabled }) });
      resource.reload();
      window.dispatchEvent(new Event("mcp-settings-updated"));
      notify(enabled ? "MCP access enabled" : "MCP access disabled");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="MCP access"
        description="Optional access for external MCP clients using personal keys."
        action={<Settings2 />}
      />
      {resource.loading ? (
        <p className="muted" role="status">
          Loading MCP settings…
        </p>
      ) : resource.error ? (
        <div>
          <p className="field-error" role="alert">
            {resource.error}
          </p>
          <Button type="button" variant="outline" onClick={resource.reload}>
            Retry
          </Button>
        </div>
      ) : (
        <form className="form-grid" onSubmit={save}>
          <p className="muted small">
            MCP is disabled by default. Enable it to let users generate personal
            keys and connect clients within their existing permissions.
          </p>
          <label className="checkbox-field">
            <input
              type="checkbox"
              role="switch"
              checked={enabled}
              disabled={busy}
              onChange={(event) => setSelection(event.target.checked)}
            />
            Enable MCP access
          </label>
          <p className="muted small">
            Disabling MCP hides key management and blocks new keys and all MCP
            requests immediately. Existing keys remain stored for later use or
            revocation.
          </p>
          {error ? (
            <p className="field-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="form-actions">
            <Button loading={busy}>
              <Save />
              Save MCP setting
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
