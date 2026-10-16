"use client";
import { useState, FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FolderGit2,
  LockKeyhole,
  Globe,
  Plus,
  Search,
  ArrowUpRight,
  Building2,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { PageHeader } from "@/components/page-header";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";
import { formatDate } from "@/lib/utils";
import type { Repository } from "@/types/api";
import { ImportRepositoryButton } from "./import-repository-button";
import {
  RepositoryOwnerFields,
  type RepositoryOrganization,
} from "./repository-owner-fields";

export function RepositoryCards({
  repositories,
}: {
  repositories: Repository[];
}) {
  return (
    <div className="repository-grid">
      {repositories.map((repo) => (
        <Link
          className="repository-link"
          key={repo.id}
          href={`/repositories/${repo.id}`}
        >
          <Card>
            <div className="split">
              <div className="repo-symbol">
                {repo.owner_type === "organization" ? (
                  <Building2 />
                ) : (
                  <FolderGit2 />
                )}
              </div>
              <span className="badge">
                {repo.visibility === "private" ? <LockKeyhole /> : <Globe />}
                {repo.visibility}
              </span>
            </div>
            <h2 className="repo-title">
              <span className="muted">{repo.owner} / </span>
              {repo.name}
            </h2>
            <p className="muted repo-description">
              {repo.description || "No description provided."}
            </p>
            <div className="split small muted">
              <span>Created {formatDate(repo.created_at)}</span>
              <ArrowUpRight />
            </div>
          </Card>
        </Link>
      ))}
    </div>
  );
}
export function CreateRepositoryButton({
  organization,
}: { organization?: RepositoryOrganization } = {}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      const repo = await api<Repository>("/repositories", {
        method: "POST",
        body: json({
          name: form.get("name"),
          description: form.get("description"),
          visibility: form.get("visibility"),
          initialize: form.get("initialize") === "on",
          organization: form.get("organization") || null,
        }),
      });
      setOpen(false);
      router.push(`/repositories/${repo.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <Plus />
        New repository
      </Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Create a repository"
        description="A new home for your next project."
      >
        <form className="form-grid" onSubmit={submit}>
          <Field
            label="Repository name"
            hint="Lowercase letters, numbers, underscores and hyphens."
          >
            <Input
              name="name"
              required
              pattern="[a-z0-9][a-z0-9_-]*"
              maxLength={100}
              autoFocus
            />
          </Field>
          <Field label="Description">
            <Textarea name="description" maxLength={500} />
          </Field>
          <RepositoryOwnerFields organization={organization} disabled={busy} />
          <label className="checkbox-field">
            <input type="checkbox" name="initialize" defaultChecked />
            Initialize with a README
          </label>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="form-actions">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button loading={busy}>Create repository</Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
export function RepositoryList({
  publicOnly = false,
}: {
  publicOnly?: boolean;
}) {
  const resource = useResource<Repository[]>(
    publicOnly ? "/repositories?scope=public" : "/repositories",
  );
  const [query, setQuery] = useState("");
  const [visibility, setVisibility] = useState("all");
  const filtered =
    resource.data?.filter(
      (repo) =>
        `${repo.owner}/${repo.name} ${repo.description}`
          .toLowerCase()
          .includes(query.toLowerCase()) &&
        (visibility === "all" || repo.visibility === visibility),
    ) ?? [];
  return (
    <>
      <PageHeader
        title={publicOnly ? "Explore repositories" : "Repositories"}
        description={
          publicOnly
            ? "Discover public code and projects from the Forge community."
            : "Build, share, and collaborate on your code."
        }
        actions={
          !publicOnly && (
            <>
              <ImportRepositoryButton />
              <CreateRepositoryButton />
            </>
          )
        }
      />
      <div className="repo-toolbar">
        <div className="search-input">
          <Search />
          <Input
            aria-label="Search repositories"
            placeholder="Search repositories…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        {!publicOnly && (
          <Select
            aria-label="Filter visibility"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value)}
          >
            <option value="all">All repositories</option>
            <option value="private">Private</option>
            <option value="public">Public</option>
          </Select>
        )}
      </div>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState message={resource.error} retry={resource.reload} />
      ) : filtered.length ? (
        <RepositoryCards repositories={filtered} />
      ) : (
        <Card>
          <Empty
            title="No repositories found"
            description={
              query
                ? "Try another search."
                : publicOnly
                  ? "Public repositories will appear here when they are shared."
                  : "Create your first repository to start collaborating."
            }
          />
        </Card>
      )}
    </>
  );
}
