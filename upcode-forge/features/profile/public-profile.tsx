"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import {
  Building2,
  CalendarDays,
  Copy,
  ExternalLink,
  FolderGit2,
  GitCommitHorizontal,
  Globe,
  Link2,
  Mail,
  MapPin,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/avatar";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/form";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useToast } from "@/components/ui/toast";
import { useResource } from "@/hooks/use-resource";
import { formatDate } from "@/lib/utils";
import type { PublicProfile as Profile } from "@/types/api";
import { ActivityCalendar } from "./activity-calendar";

export function PublicProfile({ username }: { username: string }) {
  const [year, setYear] = useState<number | null>(null);
  const resource = useResource<Profile>(
    `/profiles/${encodeURIComponent(username)}${year === null ? "" : `?year=${year}`}`,
  );
  const { notify } = useToast();
  const profile = resource.data;
  async function copy(value: string, message: string) {
    try {
      await navigator.clipboard.writeText(value);
      notify(message);
    } catch {
      notify(
        "Could not copy. Select and copy the URL from your browser.",
        "error",
      );
    }
  }
  return (
    <div className="public-profile-page">
      <header className="public-profile-nav">
        <Link href="/" aria-label="Upcode Forge home">
          <Image
            src="/logo.png"
            alt="Upcode Forge"
            width={714}
            height={631}
            className="public-profile-logo"
            sizes="46px"
            priority
          />
        </Link>
        <Button asChild variant="ghost">
          <Link href="/explore">Explore organizations</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/dashboard">
            Open workspace <ExternalLink />
          </Link>
        </Button>
      </header>
      <main className="public-profile-main">
        {resource.loading ? (
          <Loading />
        ) : resource.error ? (
          <ErrorState message={resource.error} retry={resource.reload} />
        ) : (
          profile && (
            <div className="public-profile-grid">
              <aside>
                <Card className="public-profile-identity">
                  <Avatar
                    name={profile.display_name}
                    src={profile.avatar_url}
                    className="public-profile-avatar"
                  />
                  <h1>{profile.display_name}</h1>
                  <p className="muted public-profile-handle">
                    @{profile.username}
                  </p>
                  {profile.bio && (
                    <p className="public-profile-bio">{profile.bio}</p>
                  )}
                  <ul className="public-profile-facts">
                    {profile.company && (
                      <li>
                        <Building2 />
                        <span>{profile.company}</span>
                      </li>
                    )}
                    {profile.location && (
                      <li>
                        <MapPin />
                        <span>{profile.location}</span>
                      </li>
                    )}
                    {profile.public_email && (
                      <li>
                        <Mail />
                        <a href={`mailto:${profile.public_email}`}>
                          {profile.public_email}
                        </a>
                      </li>
                    )}
                    {profile.website && (
                      <li>
                        <Globe />
                        <a
                          href={profile.website}
                          target="_blank"
                          rel="noopener noreferrer me"
                        >
                          {profile.website}
                        </a>
                      </li>
                    )}
                    <li>
                      <CalendarDays />
                      <span>Joined {formatDate(profile.created_at)}</span>
                    </li>
                  </ul>
                  {profile.social_links.length > 0 && (
                    <div className="public-profile-socials">
                      {profile.social_links.map((link, index) => (
                        <a
                          key={`${link.url}-${index}`}
                          href={link.url}
                          target="_blank"
                          rel="noopener noreferrer me"
                        >
                          <Link2 />
                          <span>{link.label}</span>
                          <ExternalLink />
                        </a>
                      ))}
                    </div>
                  )}
                  {!!profile.organizations?.length && (
                    <section
                      className="profile-organizations"
                      aria-label="Organizations"
                    >
                      <h2>Organizations</h2>
                      <div className="organization-badges">
                        {profile.organizations.map((organization) => (
                          <Link
                            key={organization.id}
                            href={`/o/${organization.slug}`}
                            title={`${organization.name}${organization.visibility === "private" ? " (private)" : ""}`}
                            aria-label={organization.name}
                          >
                            <Avatar
                              name={organization.name}
                              src={organization.avatar_url}
                            />
                          </Link>
                        ))}
                      </div>
                    </section>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      void copy(
                        window.location.origin + `/u/${profile.username}`,
                        "Profile link copied",
                      )
                    }
                  >
                    <Copy /> Share profile
                  </Button>
                </Card>
              </aside>
              <div className="public-profile-content">
                <div className="profile-stat-grid">
                  <Card>
                    <GitCommitHorizontal />
                    <strong>{profile.activity.total.toLocaleString()}</strong>
                    <span>Contributions in {profile.activity.year}</span>
                  </Card>
                  <Card>
                    <FolderGit2 />
                    <strong>{profile.repository_count.toLocaleString()}</strong>
                    <span>Public repositories</span>
                  </Card>
                  <Card>
                    <CalendarDays />
                    <strong>
                      {profile.activity.longest_streak}
                      <small> days</small>
                    </strong>
                    <span>Longest streak in {profile.activity.year}</span>
                  </Card>
                </div>
                <Card>
                  <CardHeader
                    title="Contribution activity"
                    description="Public and private contributions. Private repository details stay hidden."
                    action={
                      <Select
                        aria-label="Contribution year"
                        value={profile.activity.year}
                        onChange={(event) =>
                          setYear(Number(event.target.value))
                        }
                      >
                        {profile.activity.available_years.map((value) => (
                          <option key={value} value={value}>
                            {value}
                          </option>
                        ))}
                      </Select>
                    }
                  />
                  <ActivityCalendar activity={profile.activity} />
                  <div
                    className="activity-breakdown muted small"
                    aria-label="Public contributions by type and private contribution count"
                  >
                    <span>Public:</span>
                    <span>{profile.activity.totals.commits} commits</span>
                    <span>
                      {profile.activity.totals.repositories} repositories
                    </span>
                    <span>{profile.activity.totals.issues} issues</span>
                    <span>{profile.activity.totals.pulls} pull requests</span>
                    <span>{profile.activity.totals.comments} comments</span>
                    <span className="private-contributions">
                      {profile.activity.private_total} private contributions
                    </span>
                  </div>
                </Card>
                <section aria-labelledby="public-repositories-heading">
                  <div className="public-repositories-heading">
                    <h2 id="public-repositories-heading">
                      Public repositories{" "}
                      <span className="badge">{profile.repository_count}</span>
                    </h2>
                    <p className="muted small">
                      Clone without an account. Sign in to browse code in Forge.
                    </p>
                  </div>
                  {profile.repositories.length ? (
                    <div className="public-repository-grid">
                      {profile.repositories.map((repo) => (
                        <Card key={repo.id}>
                          <div className="split">
                            <FolderGit2 />
                            <span className="badge">
                              <Globe /> Public
                            </span>
                          </div>
                          <h3 className="repo-title">
                            <Link href={`/repositories/${repo.id}`}>
                              {repo.name}
                            </Link>
                          </h3>
                          <p className="muted repo-description">
                            {repo.description || "No description provided."}
                          </p>
                          <div className="split small muted">
                            <span>{repo.default_branch}</span>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                void copy(repo.clone_url, "Clone URL copied")
                              }
                              aria-label={`Copy clone URL for ${repo.name}`}
                            >
                              <Copy /> Clone URL
                            </Button>
                          </div>
                        </Card>
                      ))}
                    </div>
                  ) : (
                    <Card>
                      <Empty
                        title="No public repositories yet"
                        description="Public projects will appear here when they are shared."
                      />
                    </Card>
                  )}
                  {profile.repository_count > profile.repositories.length && (
                    <p className="muted small">
                      Showing the {profile.repositories.length} most recent
                      public repositories.
                    </p>
                  )}
                </section>
              </div>
            </div>
          )
        )}
      </main>
    </div>
  );
}
