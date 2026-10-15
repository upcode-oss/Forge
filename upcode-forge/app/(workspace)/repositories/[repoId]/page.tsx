import { RepositoryWorkspace } from "@/features/repositories/repository-workspace";
export default async function Page({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return <RepositoryWorkspace id={repoId} />;
}
