"use client";
import { FormEvent, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import {
  ArrowLeft,
  Check,
  CircleDot,
  Code2,
  Copy,
  FileCode,
  Folder,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
  LockKeyhole,
  Plus,
  Settings,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";
import { formatDate } from "@/lib/utils";
import type { Commit, Repository, Ticket, TreeEntry } from "@/types/api";

export function Diff({ value }: { value: string }) {
  return (
    <pre className="code-view diff-view">
      {value.split("\n").map((line, i) => (
        <div
          key={i}
          className={
            line.startsWith("+")
              ? "diff-add"
              : line.startsWith("-")
                ? "diff-remove"
                : line.startsWith("@@")
                  ? "diff-hunk"
                  : ""
          }
        >
          {line || " "}
        </div>
      ))}
    </pre>
  );
}

function CodeBrowser({
  repo,
  branches,
}: {
  repo: Repository;
  branches: string[];
}) {
  const [branch, setBranch] = useState(
    branches.includes(repo.default_branch) ? repo.default_branch : branches[0],
  );
  const [path, setPath] = useState("");
  const [file, setFile] = useState("");
  const tree = useResource<TreeEntry[]>(
    `/repositories/${repo.id}/tree?ref=${encodeURIComponent(branch)}&path=${encodeURIComponent(path)}`,
  );
  const blob = useResource<{ content: string; binary: boolean; size: number }>(
    file
      ? `/repositories/${repo.id}/blob?ref=${encodeURIComponent(branch)}&path=${encodeURIComponent(file)}`
      : null,
  );
  const readmeName = tree.data?.find(
    (v) => v.name.toLowerCase() === "readme.md",
  )?.name;
  const readme = useResource<{ content: string; binary: boolean }>(
    !file && readmeName
      ? `/repositories/${repo.id}/blob?ref=${encodeURIComponent(branch)}&path=${encodeURIComponent([path, readmeName].filter(Boolean).join("/"))}`
      : null,
  );
  const parts = (file || path).split("/").filter(Boolean);
  return (
    <>
      <div className="repo-toolbar">
        <div className="branch-picker">
          <GitBranch />
          <Select
            aria-label="Choose branch"
            value={branch}
            onChange={(e) => {
              setBranch(e.target.value);
              setPath("");
              setFile("");
            }}
          >
            {branches.map((b) => (
              <option key={b}>{b}</option>
            ))}
          </Select>
        </div>
        <span className="muted small">
          {branches.length} {branches.length === 1 ? "branch" : "branches"}
        </span>
      </div>
      <div className="breadcrumbs">
        <button
          onClick={() => {
            setPath("");
            setFile("");
          }}
        >
          {repo.name}
        </button>
        {parts.map((part, i) => (
          <span key={i}>
            {" "}
            /{" "}
            <button
              onClick={() => {
                setPath(parts.slice(0, i + 1).join("/"));
                setFile("");
              }}
              disabled={!!file && i === parts.length - 1}
            >
              {part}
            </button>
          </span>
        ))}
      </div>
      {file ? (
        <Card className="file-card">
          <CardHeader
            title={file.split("/").pop()!}
            description={
              blob.data ? `${blob.data.size.toLocaleString()} bytes` : undefined
            }
            action={
              <Button variant="outline" size="sm" onClick={() => setFile("")}>
                <ArrowLeft />
                Back to files
              </Button>
            }
          />
          {blob.loading ? (
            <Loading />
          ) : blob.error ? (
            <ErrorState message={blob.error} retry={blob.reload} />
          ) : blob.data?.binary ? (
            <Empty
              title="Binary file"
              description="Clone the repository to open this file."
            />
          ) : (
            <pre className="code-view numbered-code">
              {blob.data?.content.split("\n").map((line, i) => (
                <div key={i}>
                  <span aria-hidden>{i + 1}</span>
                  <code>{line || " "}</code>
                </div>
              ))}
            </pre>
          )}
        </Card>
      ) : (
        <>
          <Card className="file-card">
            {tree.loading ? (
              <Loading />
            ) : tree.error ? (
              <ErrorState message={tree.error} retry={tree.reload} />
            ) : (
              <div className="file-list">
                {path && (
                  <button
                    className="file-row"
                    onClick={() =>
                      setPath(path.split("/").slice(0, -1).join("/"))
                    }
                  >
                    <Folder />
                    ..
                  </button>
                )}
                {tree.data?.map((entry) => (
                  <button
                    className="file-row"
                    key={entry.name}
                    onClick={() => {
                      const next = [path, entry.name].filter(Boolean).join("/");
                      if (entry.kind === "tree") setPath(next);
                      else if (entry.kind === "blob") setFile(next);
                    }}
                    disabled={entry.kind === "commit"}
                  >
                    {entry.kind === "tree" ? <Folder /> : <FileCode />}
                    <span>{entry.name}</span>
                    <small className="muted mono">
                      {entry.mode === "120000"
                        ? "symlink"
                        : entry.kind === "commit"
                          ? "submodule"
                          : entry.oid.slice(0, 7)}
                    </small>
                  </button>
                ))}
              </div>
            )}
          </Card>
          {readme.data && !readme.data.binary && (
            <Card className="readme-card">
              <CardHeader title="README.md" />
              <div className="markdown-preview">
                <ReactMarkdown>{readme.data.content}</ReactMarkdown>
              </div>
            </Card>
          )}
        </>
      )}
    </>
  );
}

function CommitHistory({
  repo,
  branches,
}: {
  repo: Repository;
  branches: string[];
}) {
  const [branch, setBranch] = useState(repo.default_branch);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const commits = useResource<Commit[]>(
    `/repositories/${repo.id}/commits?ref=${encodeURIComponent(branch)}&offset=${offset}`,
  );
  const detail = useResource<{ diff: string }>(
    selected ? `/repositories/${repo.id}/commits/${selected}` : null,
  );
  return (
    <>
      <div className="repo-toolbar">
        <div className="branch-picker">
          <GitBranch />
          <Select
            aria-label="Commit branch"
            value={branch}
            onChange={(e) => {
              setBranch(e.target.value);
              setOffset(0);
            }}
          >
            {branches.map((b) => (
              <option key={b}>{b}</option>
            ))}
          </Select>
        </div>
      </div>
      <Card>
        {commits.loading ? (
          <Loading />
        ) : commits.error ? (
          <ErrorState message={commits.error} retry={commits.reload} />
        ) : (
          commits.data?.map((c) => (
            <button
              className="commit-row"
              key={c.sha}
              onClick={() => setSelected(c.sha)}
            >
              <GitCommitHorizontal />
              <div>
                <strong>{c.subject}</strong>
                <span className="muted small">
                  {c.author} committed {formatDate(c.date, true)}
                </span>
              </div>
              <code>{c.sha.slice(0, 7)}</code>
            </button>
          ))
        )}
        <div className="form-actions">
          <Button
            variant="outline"
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - 30))}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            disabled={(commits.data?.length ?? 0) < 30}
            onClick={() => setOffset((o) => o + 30)}
          >
            Next
          </Button>
        </div>
      </Card>
      <Dialog
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected("");
        }}
        title={`Commit ${selected.slice(0, 7)}`}
        description="Commit details and changes."
      >
        {detail.loading ? (
          <Loading />
        ) : detail.error ? (
          <ErrorState message={detail.error} />
        ) : (
          <Diff value={detail.data?.diff ?? ""} />
        )}
      </Dialog>
    </>
  );
}

function TicketDetail({
  repo,
  id,
  back,
  updated,
}: {
  repo: Repository;
  id: number;
  back: () => void;
  updated: () => void;
}) {
  const resource = useResource<Ticket>(
    `/repositories/${repo.id}/tickets/${id}`,
  );
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();
  const ticket = resource.data;
  const diff = useResource<{ diff: string }>(
    ticket?.kind === "pull"
      ? `/repositories/${repo.id}/tickets/${id}/diff`
      : null,
  );
  const write = repo.role !== "read";
  async function change(action: string) {
    setBusy(true);
    try {
      await api(`/repositories/${repo.id}/tickets/${id}/${action}`, {
        method: action === "merge" ? "POST" : "PUT",
      });
      resource.reload();
      updated();
      notify(action === "merge" ? "Pull request merged" : "Status updated");
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function comment(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = new FormData(form).get("body");
    setBusy(true);
    try {
      await api(`/repositories/${repo.id}/tickets/${id}/comments`, {
        method: "POST",
        body: json({ body }),
      });
      form.reset();
      resource.reload();
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button variant="ghost" onClick={back}>
        <ArrowLeft />
        Back to list
      </Button>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState message={resource.error} retry={resource.reload} />
      ) : (
        ticket && (
          <>
            <div className="ticket-heading">
              <h2>
                {ticket.title} <span className="muted">#{ticket.id}</span>
              </h2>
              <div className="inline-list">
                <span
                  className={`badge badge-${ticket.state === "open" ? "success" : "info"}`}
                >
                  {ticket.state}
                </span>
                <span className="muted small">
                  Opened by {ticket.author} ·{" "}
                  {formatDate(ticket.created_at, true)}
                </span>
              </div>
              {ticket.kind === "pull" && (
                <p className="mono muted small">
                  {ticket.source_branch} → {ticket.target_branch}
                </p>
              )}
            </div>
            <Card className="readme-card">
              <div className="markdown-preview">
                <ReactMarkdown>
                  {ticket.body || "No description provided."}
                </ReactMarkdown>
              </div>
            </Card>
            {ticket.kind === "pull" && (
              <Card className="readme-card">
                <CardHeader
                  title="Changes"
                  description={`${ticket.source_branch} → ${ticket.target_branch}`}
                />
                {diff.loading ? (
                  <Loading />
                ) : diff.error ? (
                  <ErrorState message={diff.error} retry={diff.reload} />
                ) : (
                  <Diff value={diff.data?.diff || "No changes."} />
                )}
                {repo.role === "maintain" && ticket.state === "open" && (
                  <div className="form-actions">
                    <Button loading={busy} onClick={() => void change("merge")}>
                      <GitPullRequest />
                      Merge pull request
                    </Button>
                  </div>
                )}
              </Card>
            )}
            {ticket.comments?.map((c) => (
              <Card className="readme-card" key={c.id}>
                <div className="split small">
                  <strong>{c.author}</strong>
                  <span className="muted">
                    {formatDate(c.created_at, true)}
                  </span>
                </div>
                <div className="markdown-preview">
                  <ReactMarkdown>{c.body}</ReactMarkdown>
                </div>
              </Card>
            ))}
            {write && (
              <Card>
                <form className="form-grid" onSubmit={comment}>
                  <Field label="Leave a comment">
                    <Textarea
                      name="body"
                      maxLength={20000}
                      required
                      placeholder="Write your comment… Markdown is supported."
                    />
                  </Field>
                  <div className="form-actions">
                    {ticket.state !== "merged" && (
                      <Button
                        type="button"
                        variant="outline"
                        disabled={busy}
                        onClick={() =>
                          void change(
                            `state?state=${ticket.state === "open" ? "closed" : "open"}`,
                          )
                        }
                      >
                        {ticket.state === "open" ? "Close" : "Reopen"}
                      </Button>
                    )}
                    <Button loading={busy}>Comment</Button>
                  </div>
                </form>
              </Card>
            )}
          </>
        )
      )}
    </>
  );
}

function Tickets({
  repo,
  kind,
  branches,
}: {
  repo: Repository;
  kind: "issue" | "pull";
  branches: string[];
}) {
  const resource = useResource<Ticket[]>(
    `/repositories/${repo.id}/tickets?kind=${kind}`,
  );
  const [selected, setSelected] = useState<number | null>(null);
  const [filter, setFilter] = useState("open");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const name = kind === "issue" ? "issue" : "pull request";
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      const item = await api<Ticket>(`/repositories/${repo.id}/tickets`, {
        method: "POST",
        body: json({ ...Object.fromEntries(form), kind }),
      });
      setOpen(false);
      resource.reload();
      setSelected(item.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (selected)
    return (
      <TicketDetail
        repo={repo}
        id={selected}
        back={() => setSelected(null)}
        updated={resource.reload}
      />
    );
  const filtered =
    resource.data?.filter((t) => filter === "all" || t.state === filter) ?? [];
  return (
    <>
      <div className="repo-toolbar">
        <div className="segmented">
          {[
            "open",
            "closed",
            ...(kind === "pull" ? ["merged"] : []),
            "all",
          ].map((state) => (
            <Button
              key={state}
              variant={state === filter ? "default" : "ghost"}
              size="sm"
              onClick={() => setFilter(state)}
            >
              {state[0].toUpperCase() + state.slice(1)}
            </Button>
          ))}
        </div>
        {repo.role !== "read" && (
          <Button onClick={() => setOpen(true)}>
            <Plus />
            New {name}
          </Button>
        )}
      </div>
      <Card>
        {resource.loading ? (
          <Loading />
        ) : resource.error ? (
          <ErrorState message={resource.error} retry={resource.reload} />
        ) : filtered.length ? (
          filtered.map((t) => (
            <button
              className="ticket-row"
              key={t.id}
              onClick={() => setSelected(t.id)}
            >
              {kind === "pull" ? <GitPullRequest /> : <CircleDot />}
              <div>
                <strong>{t.title}</strong>
                <span className="muted small">
                  #{t.id} opened {formatDate(t.created_at)} by {t.author}
                </span>
              </div>
              <span className="badge">{t.state}</span>
            </button>
          ))
        ) : (
          <Empty
            title={`No ${filter === "all" ? "" : filter + " "}${name}s`}
            description={`Use this space to ${kind === "issue" ? "track work and discuss improvements" : "review and merge branch changes"}.`}
          />
        )}
      </Card>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={`New ${name}`}
        description={
          kind === "pull"
            ? "Compare branches within this repository."
            : "Track a bug, idea, or improvement."
        }
      >
        <form className="form-grid" onSubmit={create}>
          <Field label="Title">
            <Input name="title" required maxLength={200} autoFocus />
          </Field>
          {kind === "pull" && (
            <div className="form-grid two">
              <Field label="Source branch">
                <Select
                  name="source_branch"
                  required
                  defaultValue={branches.find((b) => b !== repo.default_branch)}
                >
                  {branches.map((b) => (
                    <option key={b}>{b}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Target branch">
                <Select
                  name="target_branch"
                  defaultValue={repo.default_branch}
                  required
                >
                  {branches.map((b) => (
                    <option key={b}>{b}</option>
                  ))}
                </Select>
              </Field>
            </div>
          )}
          <Field label="Description" hint="Markdown is supported.">
            <Textarea name="body" maxLength={50000} />
          </Field>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="form-actions">
            <Button loading={busy}>Create {name}</Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

function RepositorySettings({
  repo,
  branches,
  reload,
}: {
  repo: Repository;
  branches: string[];
  reload: () => void;
}) {
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const members = useResource<{ id: number; username: string; role: string }[]>(
    `/repositories/${repo.id}/members`,
  );
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    try {
      await api(`/repositories/${repo.id}`, {
        method: "PUT",
        body: json(Object.fromEntries(new FormData(e.currentTarget))),
      });
      reload();
      notify("Repository updated");
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    setBusy(true);
    try {
      await api(`/repositories/${repo.id}/members`, {
        method: "PUT",
        body: json(Object.fromEntries(new FormData(form))),
      });
      form.reset();
      members.reload();
      notify("Member access updated");
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: number) {
    try {
      await api(`/repositories/${repo.id}/members/${id}`, { method: "DELETE" });
      members.reload();
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }
  return (
    <div className="content-grid">
      <Card>
        <CardHeader
          title="Repository settings"
          description="Configure visibility and the default branch."
        />
        <form className="form-grid" onSubmit={save}>
          <Field label="Description">
            <Textarea
              name="description"
              defaultValue={repo.description}
              maxLength={500}
            />
          </Field>
          <Field
            label="Visibility"
            hint="Public repositories can be cloned without authentication."
          >
            <Select name="visibility" defaultValue={repo.visibility}>
              <option value="private">Private</option>
              <option value="public">Public</option>
            </Select>
          </Field>
          <Field label="Default branch">
            <Select name="default_branch" defaultValue={repo.default_branch}>
              {branches.length ? (
                branches.map((b) => <option key={b}>{b}</option>)
              ) : (
                <option>{repo.default_branch}</option>
              )}
            </Select>
          </Field>
          <div className="form-actions">
            <Button loading={busy}>Save changes</Button>
          </div>
        </form>
      </Card>
      <Card>
        <CardHeader
          title="Collaborators"
          description="The owner and instance administrators always have maintain access."
        />
        <p className="small muted">
          Read: browse and clone. Write: push, issues, comments, and pull
          requests. Maintain: merge and manage access.
        </p>
        {members.loading ? (
          <Loading />
        ) : members.error ? (
          <ErrorState message={members.error} retry={members.reload} />
        ) : (
          members.data?.map((m) => (
            <div className="member-row split" key={m.id}>
              <strong>@{m.username}</strong>
              <span className="badge">{m.role}</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void remove(m.id)}
              >
                Remove
              </Button>
            </div>
          ))
        )}
        <div className="divider" />
        <form className="form-grid" onSubmit={add}>
          <Field label="Username">
            <Input name="username" required placeholder="Existing Forge user" />
          </Field>
          <Field label="Access level">
            <Select name="role">
              <option value="read">Read</option>
              <option value="write">Write</option>
              <option value="maintain">Maintain</option>
            </Select>
          </Field>
          <Button loading={busy}>
            <Plus />
            Add or update collaborator
          </Button>
        </form>
      </Card>
    </div>
  );
}

export function RepositoryWorkspace({ id }: { id: string }) {
  const resource = useResource<Repository>(`/repositories/${id}`);
  const branchResource = useResource<string[]>(`/repositories/${id}/branches`);
  const [tab, setTab] = useState("code");
  const [copied, setCopied] = useState(false);
  const { notify } = useToast();
  const repo = resource.data;
  const branches = branchResource.data ?? [];
  if (resource.loading) return <Loading />;
  if (resource.error)
    return <ErrorState message={resource.error} retry={resource.reload} />;
  if (!repo) return null;
  async function copy() {
    try {
      await navigator.clipboard.writeText(repo!.clone_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      notify("Select and copy the clone URL manually.", "error");
    }
  }
  return (
    <>
      <Link href="/repositories" className="text-link small">
        <ArrowLeft />
        All repositories
      </Link>
      <div className="repository-heading">
        <PageHeader
          title={`${repo.owner} / ${repo.name}`}
          description={
            repo.description || "Your code, versioned and connected."
          }
          actions={
            <span className="badge">
              <LockKeyhole />
              {repo.visibility}
            </span>
          }
        />
      </div>
      <div className="clone-bar">
        <span className="small muted">HTTP clone</span>
        <code>{repo.clone_url}</code>
        <Button variant="outline" size="sm" onClick={copy}>
          {copied ? <Check /> : <Copy />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <div
        className="repo-tabs"
        role="tablist"
        aria-label="Repository sections"
      >
        {[
          { key: "code", label: "Code", icon: Code2 },
          { key: "commits", label: "Commits", icon: GitCommitHorizontal },
          { key: "issues", label: "Issues", icon: CircleDot },
          { key: "pulls", label: "Pull requests", icon: GitPullRequest },
          ...(repo.role === "maintain"
            ? [{ key: "settings", label: "Settings", icon: Settings }]
            : []),
        ].map((item) => (
          <button
            role="tab"
            aria-selected={tab === item.key}
            key={item.key}
            className={tab === item.key ? "active" : ""}
            onClick={() => setTab(item.key)}
          >
            <item.icon />
            {item.label}
          </button>
        ))}
      </div>
      {branchResource.loading ? (
        <Loading />
      ) : branchResource.error ? (
        <ErrorState
          message={branchResource.error}
          retry={branchResource.reload}
        />
      ) : tab === "settings" ? (
        <RepositorySettings
          repo={repo}
          branches={branches}
          reload={resource.reload}
        />
      ) : tab === "issues" || tab === "pulls" ? (
        <Tickets
          key={tab}
          repo={repo}
          kind={tab === "issues" ? "issue" : "pull"}
          branches={branches}
        />
      ) : !branches.length ? (
        <Card>
          <Empty
            title="Your repository is empty"
            description="Push your first commit to get started."
          />
          <pre className="code-view">{`git clone ${repo.clone_url}\ncd ${repo.name}\ngit switch --orphan ${repo.default_branch}\necho "# ${repo.name}" > README.md\ngit add README.md\ngit commit -m "Initial commit"\ngit push -u origin ${repo.default_branch}`}</pre>
          <p className="muted small">
            Use your username and an access token from Profile & Access Tokens
            when Git asks for credentials.
          </p>
          <Button variant="outline" onClick={branchResource.reload}>
            Refresh branches
          </Button>
        </Card>
      ) : tab === "commits" ? (
        <CommitHistory repo={repo} branches={branches} />
      ) : (
        <CodeBrowser repo={repo} branches={branches} />
      )}
    </>
  );
}
