"use client";
import Link from "next/link";
import {
  CircleDot,
  FolderGit2,
  GitPullRequest,
  ArrowRight,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useAuth } from "@/features/auth/auth-context";
import { useResource } from "@/hooks/use-resource";
import {
  CreateRepositoryButton,
  RepositoryCards,
} from "@/features/repositories/repository-list";
import type { Repository } from "@/types/api";

export default function Dashboard() {
  const user = useAuth();
  const stats = useResource<{
    repositories: number;
    issues: number;
    pulls: number;
  }>("/dashboard");
  const repos = useResource<Repository[]>("/repositories");
  return (
    <>
      <PageHeader
        title="Dashboard"
        description={`Welcome back, ${user.display_name}. Here’s your development workspace.`}
        actions={<CreateRepositoryButton />}
      />
      {stats.error ? (
        <ErrorState message={stats.error} retry={stats.reload} />
      ) : (
        <div className="metrics-grid">
          {(
            [
              { key: "repositories", label: "Repositories", icon: FolderGit2 },
              { key: "issues", label: "Open issues", icon: CircleDot },
              {
                key: "pulls",
                label: "Open pull requests",
                icon: GitPullRequest,
              },
            ] as const
          ).map((item) => (
            <Card key={item.key} className="metric">
              <span className="metric-label">{item.label}</span>
              <strong className="metric-value">
                {stats.data ? stats.data[item.key] : "…"}
              </strong>
              <div className="metric-icon">
                <item.icon />
              </div>
            </Card>
          ))}
        </div>
      )}
      <Card className="welcome-card">
        <div>
          <span className="eyebrow">YOUR DEVELOPMENT WORKSPACE</span>
          <h2>Great software starts with a commit.</h2>
          <p className="muted">
            Keep your code close, your team connected, and your projects moving.
          </p>
          <Link className="text-link" href="/repositories">
            Explore repositories <ArrowRight />
          </Link>
        </div>
        <FolderGit2 aria-hidden />
      </Card>
      <CardHeader
        title="Recent repositories"
        description="The latest projects you can access."
        action={
          <Link href="/repositories" className="text-link">
            View all
            <ArrowRight />
          </Link>
        }
      />
      {repos.loading ? (
        <Loading />
      ) : repos.error ? (
        <ErrorState message={repos.error} retry={repos.reload} />
      ) : repos.data?.length ? (
        <RepositoryCards repositories={repos.data.slice(0, 6)} />
      ) : (
        <Card>
          <Empty
            title="Your workspace is ready"
            description="Create your first repository and push your code."
          />
        </Card>
      )}
    </>
  );
}
