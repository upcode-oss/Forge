"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { LogOut, UserPlus, X } from "lucide-react";
import { Avatar } from "@/components/avatar";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";
import type { OrganizationMember, OrganizationRole } from "@/types/api";

export function OrganizationMembers({
  slug,
  role = null,
  username,
  onLeave,
}: {
  slug: string;
  role?: OrganizationRole | null;
  username?: string;
  onLeave?: () => void;
}) {
  const resource = useResource<OrganizationMember[]>(
    `/organizations/${slug}/members`,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState<OrganizationMember | null>(null);
  const canManage = role === "owner" || role === "maintainer";
  const roles =
    role === "owner" ? ["reader", "maintainer", "owner"] : ["reader"];
  async function save(
    event: FormEvent<HTMLFormElement>,
    member?: OrganizationMember,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    setBusy(true);
    setError("");
    try {
      await api(`/organizations/${slug}/members`, {
        method: "PUT",
        body: json({
          username: member?.username ?? values.username,
          role: values.role,
        }),
      });
      if (!member) form.reset();
      resource.reload();
      if (member && member.username === username && values.role !== member.role)
        onLeave?.();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    setError("");
    try {
      await api(
        `/organizations/${slug}/members/${encodeURIComponent(removing.username)}`,
        { method: "DELETE" },
      );
      setRemoving(null);
      resource.reload();
      if (removing.username === username) onLeave?.();
    } catch (error) {
      setRemoving(null);
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card>
      <CardHeader
        title="Members"
        description={
          canManage
            ? "Owners manage all roles. Maintainers edit the profile and manage Readers. Readers can view the organization."
            : "The people who make up this organization."
        }
      />
      {canManage && (
        <form
          className="organization-member-form"
          onSubmit={(event) => void save(event)}
        >
          <Field label="Forge username">
            <Input
              name="username"
              required
              maxLength={50}
              placeholder="username"
              disabled={busy}
            />
          </Field>
          <Field label="Role">
            <Select name="role" disabled={busy}>
              {roles.map((value) => (
                <option key={value} value={value}>
                  {value.charAt(0).toUpperCase() + value.slice(1)}
                </option>
              ))}
            </Select>
          </Field>
          <Button loading={busy}>
            <UserPlus /> Add member
          </Button>
        </form>
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState message={resource.error} retry={resource.reload} />
      ) : resource.data?.length ? (
        <ul className="organization-members">
          {resource.data.map((member) => {
            const editable =
              role === "owner" ||
              (role === "maintainer" && member.role === "reader");
            return (
              <li key={member.username}>
                <Link
                  href={`/u/${member.username}`}
                  className="organization-member-identity"
                >
                  <Avatar name={member.display_name} src={member.avatar_url} />
                  <span>
                    <strong>{member.display_name}</strong>
                    <small className="muted">@{member.username}</small>
                  </span>
                </Link>
                <div className="organization-member-actions">
                  {editable ? (
                    <form onSubmit={(event) => void save(event, member)}>
                      <Select
                        name="role"
                        aria-label={`Role for ${member.username}`}
                        defaultValue={member.role}
                        disabled={busy}
                      >
                        {roles.map((value) => (
                          <option key={value} value={value}>
                            {value.charAt(0).toUpperCase() + value.slice(1)}
                          </option>
                        ))}
                      </Select>
                      <Button size="sm" variant="outline" disabled={busy}>
                        Save role
                      </Button>
                    </form>
                  ) : (
                    <span className="badge organization-role">
                      {member.role}
                    </span>
                  )}
                  {(editable || member.username === username) && (
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={busy}
                      onClick={() => setRemoving(member)}
                      aria-label={
                        member.username === username
                          ? "Leave organization"
                          : `Remove ${member.username}`
                      }
                    >
                      {member.username === username ? <LogOut /> : <X />}
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <Empty
          title="No active members"
          description="Active organization members will appear here."
        />
      )}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => {
          if (!busy && !open) setRemoving(null);
        }}
        title={
          removing?.username === username
            ? "Leave organization?"
            : "Remove member?"
        }
        description={
          removing?.username === username
            ? "You will lose your membership. The last Owner must assign another Owner before leaving."
            : `Remove @${removing?.username ?? ""} from this organization?`
        }
        loading={busy}
        onConfirm={() => void remove()}
      />
    </Card>
  );
}
