import type { Metadata } from "next";
import {
  OrganizationList,
  OrganizationPublicHeader,
} from "@/features/organizations/organization-list";

export const metadata: Metadata = { title: "Explore organizations" };

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const { q } = await searchParams;
  return (
    <div className="public-profile-page">
      <OrganizationPublicHeader />
      <main className="public-profile-main">
        <OrganizationList
          initialQuery={typeof q === "string" ? q.slice(0, 100) : ""}
        />
      </main>
    </div>
  );
}
