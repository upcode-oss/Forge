"use client";

import { AppShell } from "@/components/app-shell";
import { PublicHeader } from "@/components/public-header";
import { AuthProvider, useOptionalAuth } from "@/features/auth/auth-context";
import { RepositoryWorkspace } from "./repository-workspace";
import { RepositoryList } from "./repository-list";

function RepositoryPageContent({ id }: { id?: string }) {
  const user = useOptionalAuth();
  const content = id ? (
    <RepositoryWorkspace id={id} publicView={!user} />
  ) : (
    <RepositoryList publicOnly={!user} />
  );
  return user ? (
    <AppShell>{content}</AppShell>
  ) : (
    <div className="public-profile-page">
      <PublicHeader />
      <main className="public-profile-main">{content}</main>
    </div>
  );
}

export function RepositoryPage({ id }: { id?: string }) {
  return (
    <AuthProvider optional>
      <RepositoryPageContent id={id} />
    </AuthProvider>
  );
}
