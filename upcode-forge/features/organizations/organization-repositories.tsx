"use client";

import Link from "next/link";
import { useState } from "react";
import { Globe, LockKeyhole } from "lucide-react";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import {
  CloneBar,
  type CloneProtocol,
} from "@/features/repositories/clone-bar";
import { CreateRepositoryButton } from "@/features/repositories/repository-list";
import { ImportRepositoryButton } from "@/features/repositories/import-repository-button";
import { useResource } from "@/hooks/use-resource";
import type { Organization, Repository } from "@/types/api";

function OrganizationRepositoryCard({
  repository,
}: {
  repository: Repository;
}) {
  const [protocol, setProtocol] = useState<CloneProtocol>("https");
  return (
    <Card>
      <div className="split">
        <h3 className="repo-title">
          <Link href={`/repositories/${repository.id}`}>{repository.name}</Link>
        </h3>
        <span className="badge">
          {repository.visibility === "private" ? <LockKeyhole /> : <Globe />}
          {repository.visibility}
        </span>
      </div>
      <p className="muted repo-description">
        {repository.description || "No description provided."}
      </p>
      <CloneBar
        httpsUrl={repository.clone_url}
        sshUrl={repository.ssh_clone_url}
        protocol={protocol}
        onProtocolChange={setProtocol}
      />
    </Card>
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
    <section className="stack" aria-label="Organization repositories">
      <Card>
        <CardHeader
          title="Repositories"
          description="Repositories you can access in this organization."
          action={
            editable && (
              <div className="page-actions">
                <ImportRepositoryButton organization={organization} />
                <CreateRepositoryButton organization={organization} />
              </div>
            )
          }
        />
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
          <p className="muted small">
            {resource.data.total}{" "}
            {resource.data.total === 1 ? "repository" : "repositories"}
          </p>
        )}
      </Card>
      {!!resource.data?.items?.length && (
        <div className="organization-repository-grid">
          {resource.data.items.map((repository) => (
            <OrganizationRepositoryCard
              key={repository.id}
              repository={repository}
            />
          ))}
        </div>
      )}
      {resource.data && (resource.data.total > 30 || offset > 0) && (
        <nav className="organization-pagination" aria-label="Repository pages">
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
    </section>
  );
}
