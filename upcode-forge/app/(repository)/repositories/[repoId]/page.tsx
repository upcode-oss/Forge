import { RepositoryPage } from "@/features/repositories/repository-page";

export default async function Page({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return <RepositoryPage id={repoId} />;
}
