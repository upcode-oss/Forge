"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, Github, Gitlab } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/form";
import { api, json } from "@/services/api";
import type { Repository } from "@/types/api";
import {
  RepositoryOwnerFields,
  type RepositoryOrganization,
} from "./repository-owner-fields";

export function ImportRepositoryButton({
  organization,
}: { organization?: RepositoryOrganization } = {}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [nameEdited, setNameEdited] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    setError("");
    try {
      const repo = await api<Repository>("/repositories/import", {
        method: "POST",
        body: json({
          ...values,
          organization: values.organization || null,
          token: values.token || null,
        }),
      });
      setOpen(false);
      router.push(`/repositories/${repo.id}`);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button
        variant="outline"
        onClick={() => {
          setError("");
          setName("");
          setNameEdited(false);
          setOpen(true);
        }}
      >
        <Download /> Import repository
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!busy) setOpen(value);
        }}
        title="Import a repository"
        description="Bring an existing GitHub or GitLab repository to Forge, including its history, branches and tags."
      >
        <form className="form-grid" onSubmit={submit}>
          <div className="import-providers muted small">
            <Github /> GitHub <Gitlab /> GitLab.com
          </div>
          <Field
            label="Repository URL"
            hint="Use the HTTPS clone URL from github.com or gitlab.com."
          >
            <Input
              name="source_url"
              type="url"
              required
              maxLength={500}
              autoFocus
              disabled={busy}
              placeholder="https://github.com/owner/repository.git"
              onChange={(event) => {
                if (!nameEdited) {
                  const suggested =
                    event.target.value
                      .trim()
                      .replace(/\/$/, "")
                      .split("/")
                      .pop()
                      ?.replace(/\.git$/, "") ?? "";
                  setName(
                    suggested
                      .toLowerCase()
                      .replace(/[^a-z0-9_-]/g, "-")
                      .replace(/^[^a-z0-9]+/, "")
                      .slice(0, 100),
                  );
                }
              }}
            />
          </Field>
          <Field
            label="Repository name in Forge"
            hint="Lowercase letters, numbers, underscores and hyphens."
          >
            <Input
              name="name"
              required
              pattern="[a-z0-9][a-z0-9_-]*"
              maxLength={100}
              disabled={busy}
              value={name}
              onChange={(event) => {
                setNameEdited(true);
                setName(event.target.value);
              }}
            />
          </Field>
          <Field label="Description">
            <Textarea name="description" maxLength={500} disabled={busy} />
          </Field>
          <RepositoryOwnerFields organization={organization} disabled={busy} />
          <Field
            label="Access token (optional)"
            hint="Required for private repositories. Use a token with repository read access. It is used once and never saved."
          >
            <Input
              name="token"
              type="password"
              maxLength={500}
              autoComplete="off"
              disabled={busy}
            />
          </Field>
          <p className="muted small">
            This is a one-time Git import. Issues, pull requests, LFS files and
            provider settings are not copied.
          </p>
          {busy && (
            <p role="status" className="muted small">
              Importing repository… This can take up to three minutes.
            </p>
          )}
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
            <Button loading={busy}>Import repository</Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
