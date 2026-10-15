import type { Metadata } from "next";
import { PublicProfile } from "@/features/profile/public-profile";

type Props = { params: Promise<{ username: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { username } = await params;
  return {
    title: `@${username}`,
    description: `Public projects and contributions by @${username} on Upcode Forge.`,
  };
}

export default async function Page({ params }: Props) {
  const { username } = await params;
  return <PublicProfile username={username} />;
}
