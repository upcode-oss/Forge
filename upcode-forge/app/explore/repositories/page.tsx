import type { Metadata } from "next";
import { PublicHeader } from "@/components/public-header";
import { RepositoryList } from "@/features/repositories/repository-list";

export const metadata: Metadata = { title: "Explore repositories" };

export default function Page() {
  return (
    <div className="public-profile-page">
      <PublicHeader />
      <main className="public-profile-main">
        <RepositoryList publicOnly />
      </main>
    </div>
  );
}
