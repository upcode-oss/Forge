"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { api } from "@/services/api";
import type { Repository } from "@/types/api";

export function DeleteRepositoryCard({ repo }: { repo: Repository }) {
  const router = useRouter();
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fullName = `${repo.owner}/${repo.name}`;

  function changeOpen(next: boolean) {
    if (busy) return;
    setOpen(next);
    setConfirmation("");
    setError("");
  }

  async function remove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || confirmation !== fullName) return;
    setBusy(true);
    setError("");
    try {
      await api(`/repositories/${repo.id}`, { method: "DELETE" });
      notify("Repository deleted");
      router.replace(
        repo.owner_type === "organization"
          ? repo.owner_profile_url
          : "/repositories",
      );
      router.refresh();
    } catch (error) {
      setError((error as Error).message);
      setBusy(false);
    }
  }

  if (repo.role !== "maintain") return null;

  return (
    <Card className="repository-danger-zone">
      <CardHeader
        title="Delete repository"
        description="Permanently delete this repository, its Git history, issues, pull requests, comments, and collaborator access. This cannot be undone."
      />
      <Button variant="destructive" onClick={() => changeOpen(true)}>
        <Trash2 />
        Delete repository
      </Button>
      <Dialog
        open={open}
        onOpenChange={changeOpen}
        title={`Delete ${fullName}?`}
        description="All code, Git history, issues, pull requests, comments, and collaborator access will be permanently deleted. This cannot be undone."
      >
        <form className="form-grid" onSubmit={remove}>
          <Field label={`Type ${fullName} to confirm`}>
            <Input
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              disabled={busy}
              required
            />
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
              onClick={() => changeOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={confirmation !== fullName}
              loading={busy}
            >
              <Trash2 />
              Delete repository
            </Button>
          </div>
        </form>
      </Dialog>
    </Card>
  );
}
