import type { Metadata } from "next";
import { PublicOrganization } from "@/features/organizations/organization-pages";

export const metadata: Metadata = {
  title: "Organization",
  robots: { index: false },
};

export default async function Page({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <PublicOrganization slug={slug} />;
}
