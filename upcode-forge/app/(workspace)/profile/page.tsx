"use client";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, Plus, Trash2, UserRound } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { Dialog, ConfirmDialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { ErrorState, Loading } from "@/components/states";
import { useAuth } from "@/features/auth/auth-context";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";
import { formatDate } from "@/lib/utils";

type Token = { id: number; name: string; scope: string; expires_at: string };
export default function Profile() {
  const router = useRouter();
  const user = useAuth();
  const { notify } = useToast();
  const tokens = useResource<Token[]>("/tokens");
  const [open, setOpen] = useState(false);
  const [raw, setRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [revoking, setRevoking] = useState<Token | null>(null);
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const values = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    try {
      const result = await api<{ token: string }>("/tokens", {
        method: "POST",
        body: json({ ...values, days: Number(values.days) }),
      });
      setRaw(result.token);
      tokens.reload();
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function revoke() {
    if (!revoking) return;
    setBusy(true);
    try {
      await api(`/tokens/${revoking.id}`, { method: "DELETE" });
      tokens.reload();
      setRevoking(null);
      notify("Token revoked");
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function password(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/auth/password", {
        method: "POST",
        body: json(Object.fromEntries(new FormData(e.currentTarget))),
      });
      router.replace("/login");
    } catch (e) {
      notify((e as Error).message, "error");
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        title="Profile & Access Tokens"
        description="Manage your identity and Git authentication."
      />
      <div className="content-grid">
        <Card>
          <CardHeader title="Your profile" />
          <div className="profile-summary">
            <div className="avatar">
              <UserRound />
            </div>
            <div>
              <h2>{user.display_name}</h2>
              <p className="muted">
                @{user.username} · {user.email}
              </p>
              <span className="badge">
                {user.is_admin ? "Administrator" : "Member"}
              </span>
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader
            title="Change password"
            description="Changing your password revokes all sessions and Git tokens."
          />
          <form className="form-grid" onSubmit={password}>
            <Field label="Current password">
              <Input
                type="password"
                name="current_password"
                required
                autoComplete="current-password"
              />
            </Field>
            <Field label="New password" hint="At least 12 characters.">
              <Input
                type="password"
                name="new_password"
                required
                minLength={12}
                maxLength={256}
                autoComplete="new-password"
              />
            </Field>
            <div className="form-actions">
              <Button loading={busy}>Change password</Button>
            </div>
          </form>
        </Card>
        <Card className="wide">
          <CardHeader
            title="Git access tokens"
            description="Use your Forge username and a token as the password for Git over HTTP(S)."
            action={
              <Button
                onClick={() => {
                  setRaw("");
                  setOpen(true);
                }}
              >
                <Plus />
                Generate token
              </Button>
            }
          />
          {tokens.loading ? (
            <Loading />
          ) : tokens.error ? (
            <ErrorState message={tokens.error} retry={tokens.reload} />
          ) : tokens.data?.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Scope</th>
                    <th>Expires</th>
                    <th>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {tokens.data.map((token) => (
                    <tr key={token.id}>
                      <td>
                        <KeyRound /> {token.name}
                      </td>
                      <td>
                        <span className="badge">{token.scope}</span>
                      </td>
                      <td>{formatDate(token.expires_at)}</td>
                      <td>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setRevoking(token)}
                          aria-label={`Revoke ${token.name}`}
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
              No Git tokens yet. Generate one to push your code.
            </p>
          )}
        </Card>
      </div>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={raw ? "Your new access token" : "Generate a Git token"}
        description={
          raw
            ? "Copy this token now. It will only be shown once."
            : "Token permissions never exceed your repository access."
        }
      >
        {raw ? (
          <>
            <Input
              aria-label="New access token"
              className="mono"
              value={raw}
              readOnly
              onFocus={(e) => e.currentTarget.select()}
            />
            <p className="muted small">
              Store it in your password manager and use it when Git asks for a
              password.
            </p>
            <div className="form-actions">
              <Button
                onClick={() => {
                  setRaw("");
                  setOpen(false);
                }}
              >
                Done
              </Button>
            </div>
          </>
        ) : (
          <form className="form-grid" onSubmit={create}>
            <Field label="Token name">
              <Input
                name="name"
                required
                maxLength={100}
                placeholder="Work laptop"
              />
            </Field>
            <Field label="Scope">
              <Select name="scope">
                <option value="write">Read and write</option>
                <option value="read">Read only</option>
              </Select>
            </Field>
            <Field label="Expiration">
              <Select name="days" defaultValue="90">
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="365">1 year</option>
              </Select>
            </Field>
            <div className="form-actions">
              <Button loading={busy}>Generate token</Button>
            </div>
          </form>
        )}
      </Dialog>
      <ConfirmDialog
        open={!!revoking}
        onOpenChange={(v) => {
          if (!v) setRevoking(null);
        }}
        title="Revoke access token?"
        description={`Git clients using “${revoking?.name}” will lose access immediately.`}
        loading={busy}
        onConfirm={() => void revoke()}
      />
    </>
  );
}
