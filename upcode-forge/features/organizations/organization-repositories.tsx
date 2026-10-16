"use client";

import Link from "next/link";
import { useId, useState } from "react";
import {
  ChevronDown,
  Code2,
  FolderGit2,
  GitBranch,
  Globe,
  LockKeyhole,
} from "lucide-react";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  CloneBar,
  type CloneProtocol,
} from "@/features/repositories/clone-bar";
import { CreateRepositoryButton } from "@/features/repositories/repository-list";
import { ImportRepositoryButton } from "@/features/repositories/import-repository-button";
import { useResource } from "@/hooks/use-resource";
import { formatDate } from "@/lib/utils";
import type { Organization, Repository } from "@/types/api";

function OrganizationRepositoryRow({ repository }: { repository: Repository }) {
  const [protocol, setProtocol] = useState<CloneProtocol>("https");
  const [cloneOpen, setCloneOpen] = useState(false);
  const cloneId = useId();
  return (
    <li className="organization-repository-row">
      <div className="repo-symbol" aria-hidden="true">
        <FolderGit2 />
      </div>
      <div className="organization-repository-info">
        <div className="organization-repository-title">
          <h3>
            <Link href={`/repositories/${repository.id}`}>
              {repository.name}
            </Link>
          </h3>
          <span className="badge">
            {repository.visibility === "private" ? <LockKeyhole /> : <Globe />}
            {repository.visibility}
          </span>
        </div>
        <p className="muted organization-repository-description">
          {repository.description || "No description provided."}
        </p>
        <div className="organization-repository-meta muted small">
          <span>
            <GitBranch aria-hidden="true" />
            {repository.default_branch}
          </span>
          <span>Created {formatDate(repository.created_at)}</span>
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="organization-repository-clone-toggle"
        aria-label={`Clone ${repository.name}`}
        aria-expanded={cloneOpen}
        aria-controls={cloneId}
        onClick={() => setCloneOpen((open) => !open)}
      >
        <Code2 />
        Clone
        <ChevronDown />
      </Button>
      <div
        id={cloneId}
        className="organization-repository-clone"
        hidden={!cloneOpen}
      >
        <CloneBar
          httpsUrl={repository.clone_url}
          sshUrl={repository.ssh_clone_url}
          protocol={protocol}
          onProtocolChange={setProtocol}
        />
      </div>
    </li>
  );
}

export function OrganizationRepositories({
  organization,
}: {
  organization: Organization;
}) {
  const [offset, setOffset] = useState(0);
  const resource = useResource<{ items: Repository[]; total: number }>(
    `/organizations/${organization.slug}/repositories?offset=${offset}&limit=30`,
  );
  const editable =
    organization.role === "owner" || organization.role === "maintainer";
  return (
    <section aria-label="Organization repositories">
      <Card className="organization-repositories">
        <div className="organization-repositories-header">
          <div>
            <h2>
              <FolderGit2 aria-hidden="true" />
              Repositories
              {resource.data && (
                <span className="badge">{resource.data.total}</span>
              )}
            </h2>
            <p className="muted">Code and projects from {organization.name}.</p>
          </div>
          {editable && (
            <div className="page-actions">
              <ImportRepositoryButton organization={organization} />
              <CreateRepositoryButton organization={organization} />
            </div>
          )}
        </div>
        {!editable && organization.role === "reader" && (
          <p className="muted small">
            Owners and Maintainers can create repositories. Your organization
            role grants read access.
          </p>
        )}
        {resource.loading ? (
          <Loading />
        ) : resource.error ? (
          <ErrorState message={resource.error} retry={resource.reload} />
        ) : !resource.data?.items?.length ? (
          <Empty
            title="No repositories yet"
            description={
              editable
                ? "Create a repository or import one from GitHub or GitLab."
                : "Repositories visible to you will appear here."
            }
          />
        ) : (
          <ul className="organization-repository-list">
            {resource.data.items.map((repository) => (
              <OrganizationRepositoryRow
                key={repository.id}
                repository={repository}
              />
            ))}
          </ul>
        )}
        {resource.data && (resource.data.total > 30 || offset > 0) && (
          <nav
            className="organization-pagination"
            aria-label="Repository pages"
          >
            <Button
              variant="outline"
              disabled={offset === 0}
              onClick={() => setOffset((value) => Math.max(0, value - 30))}
            >
              Previous
            </Button>
            <span className="muted small">
              Page {Math.floor(offset / 30) + 1}
            </span>
            <Button
              variant="outline"
              disabled={offset + 30 >= resource.data.total}
              onClick={() => setOffset((value) => value + 30)}
            >
              Next
            </Button>
          </nav>
        )}
      </Card>
    </section>
  );
}
