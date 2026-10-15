"use client";
import { FormEvent, useState } from "react";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { ErrorState, Loading } from "@/components/states";
import { useAuth } from "@/features/auth/auth-context";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";
import type { User } from "@/types/api";

export default function Users() {
  const me = useAuth();
  const resource = useResource<User[]>(me.is_admin ? "/users" : null);
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<User | null>(null);
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await api("/users", {
        method: "POST",
        body: json({
          ...Object.fromEntries(form),
          is_admin: form.get("is_admin") === "on",
        }),
      });
      resource.reload();
      setOpen(false);
      notify("User created");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle() {
    if (!selected) return;
    setBusy(true);
    try {
      await api(`/users/${selected.id}/active?active=${!selected.is_active}`, {
        method: "PUT",
      });
      setSelected(null);
      resource.reload();
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
        title="Users"
        description="Manage the people in your Forge workspace."
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus />
            Add user
          </Button>
        }
      />
      <Card>
        {resource.loading ? (
          <Loading />
        ) : resource.error ? (
          <ErrorState message={resource.error} retry={resource.reload} />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {resource.data?.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <strong>{user.display_name}</strong>
                    </td>
                    <td>@{user.username}</td>
                    <td>{user.email}</td>
                    <td>
                      <span className="badge">
                        {user.is_admin ? "Administrator" : "Member"}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`badge ${user.is_active ? "badge-success" : "badge-error"}`}
                      >
                        {user.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={user.id === me.id}
                        onClick={() => setSelected(user)}
                      >
                        {user.is_active ? "Deactivate" : "Activate"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Add user"
        description="Create an account and share the initial password securely."
      >
        <form className="form-grid" onSubmit={create}>
          <Field label="Display name">
            <Input name="display_name" required maxLength={100} />
          </Field>
          <Field label="Username">
            <Input
              name="username"
              required
              pattern="[a-z][a-z0-9_-]*"
              maxLength={50}
            />
          </Field>
          <Field label="Email">
            <Input name="email" type="email" required />
          </Field>
          <Field label="Initial password" hint="At least 12 characters.">
            <Input
              name="password"
              type="password"
              required
              minLength={12}
              maxLength={256}
              autoComplete="new-password"
            />
          </Field>
          <label className="checkbox-field">
            <input type="checkbox" name="is_admin" />
            Instance administrator
          </label>
          {error && (
            <p role="alert" className="field-error">
              {error}
            </p>
          )}
          <div className="form-actions">
            <Button loading={busy}>Create user</Button>
          </div>
        </form>
      </Dialog>
      <ConfirmDialog
        open={!!selected}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
        title={`${selected?.is_active ? "Deactivate" : "Activate"} user?`}
        description={
          selected?.is_active
            ? `All sessions and Git tokens for @${selected.username} will be revoked.`
            : `@${selected?.username} will be able to sign in again.`
        }
        onConfirm={() => void toggle()}
        loading={busy}
      />
    </>
  );
}
