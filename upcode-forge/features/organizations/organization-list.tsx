"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Globe, LockKeyhole, Plus, Search, Users } from "lucide-react";
import { Avatar } from "@/components/avatar";
import { PageHeader } from "@/components/page-header";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { useResource } from "@/hooks/use-resource";
import type { OrganizationSummary } from "@/types/api";

export { PublicHeader as OrganizationPublicHeader } from "@/components/public-header";

export function OrganizationCards({
  organizations,
  mine = false,
}: {
  organizations: OrganizationSummary[];
  mine?: boolean;
}) {
  return (
    <div className="organization-grid">
      {organizations.map((organization) => (
        <Link
          className="repository-link"
          key={organization.id}
          href={
            mine
              ? `/organizations/${organization.slug}`
              : `/o/${organization.slug}`
          }
        >
          <Card className="organization-card">
            <div className="split">
              <Avatar
                name={organization.name}
                src={organization.avatar_url}
                className="organization-avatar"
              />
              <span className="badge">
                {organization.visibility === "private" ? (
                  <LockKeyhole />
                ) : (
                  <Globe />
                )}
                {organization.visibility}
              </span>
            </div>
            <div>
              <h2>{organization.name}</h2>
              <span className="muted small">@{organization.slug}</span>
            </div>
            <p className="muted organization-description">
              {organization.description || "No description provided."}
            </p>
            <div className="split small muted">
              <span className="organization-member-count">
                <Users /> {organization.member_count}{" "}
                {organization.member_count === 1 ? "member" : "members"}
              </span>
              {organization.role && (
                <span className="badge organization-role">
                  {organization.role}
                </span>
              )}
            </div>
          </Card>
        </Link>
      ))}
    </div>
  );
}

export function OrganizationList({
  mine = false,
  initialQuery = "",
}: {
  mine?: boolean;
  initialQuery?: string;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [search, setSearch] = useState(initialQuery);
  const [offset, setOffset] = useState(0);
  const resource = useResource<{ items: OrganizationSummary[]; total: number }>(
    `/organizations?scope=${mine ? "mine" : "public"}&q=${encodeURIComponent(search)}&offset=${offset}&limit=30`,
  );
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
    setSearch(query.trim());
  }
  return (
    <>
      <PageHeader
        title={mine ? "Your organizations" : "Explore organizations"}
        description={
          mine
            ? "Collaborate with your teams and manage your memberships."
            : "Find public teams and communities on Forge."
        }
        actions={
          <Button asChild>
            <Link href="/organizations/new">
              <Plus /> New organization
            </Link>
          </Button>
        }
      />
      <form className="organization-search" role="search" onSubmit={submit}>
        <Input
          type="search"
          aria-label="Search organizations"
          placeholder="Search by name, URL name or description…"
          maxLength={100}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" variant="outline">
          <Search /> Search
        </Button>
      </form>
      {mine && (
        <p className="muted small">
          Looking for a team?{" "}
          <Link href="/explore">Explore public organizations</Link>
        </p>
      )}
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState message={resource.error} retry={resource.reload} />
      ) : (
        resource.data && (
          <>
            {resource.data.items.length ? (
              <OrganizationCards
                organizations={resource.data.items}
                mine={mine}
              />
            ) : (
              <Card>
                <Empty
                  title={
                    search
                      ? "No matching organizations"
                      : mine
                        ? "You have no organizations yet"
                        : "No public organizations yet"
                  }
                  description={
                    search
                      ? "Try another name or keyword."
                      : "Create an organization to bring your team together."
                  }
                />
              </Card>
            )}
            {resource.data.total > 30 && (
              <nav
                className="organization-pagination"
                aria-label="Organization pages"
              >
                <Button
                  variant="outline"
                  disabled={offset === 0}
                  onClick={() => setOffset((v) => Math.max(0, v - 30))}
                >
                  Previous
                </Button>
                <span className="muted small">
                  {offset + 1}–{Math.min(offset + 30, resource.data.total)} of{" "}
                  {resource.data.total}
                </span>
                <Button
                  variant="outline"
                  disabled={offset + 30 >= resource.data.total}
                  onClick={() => setOffset((v) => v + 30)}
                >
                  Next
                </Button>
              </nav>
            )}
          </>
        )
      )}
    </>
  );
}
