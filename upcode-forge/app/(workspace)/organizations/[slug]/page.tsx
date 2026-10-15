import { OrganizationWorkspace } from "@/features/organizations/organization-pages";

export default async function Page({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <OrganizationWorkspace slug={slug} />;
}
