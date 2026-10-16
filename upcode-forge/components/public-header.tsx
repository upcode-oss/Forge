"use client";

import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useResource } from "@/hooks/use-resource";
import type { Instance, User } from "@/types/api";

export function PublicHeader() {
  const session = useResource<User>("/auth/me");
  const instance = useResource<Instance>("/instance");
  const signedIn = !!session.data?.username;
  return (
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
      <nav className="page-actions" aria-label="Public navigation">
        <Button asChild variant="ghost">
          <Link href="/explore/repositories">Explore repositories</Link>
        </Button>
        <Button asChild variant="ghost">
          <Link href="/explore">Explore organizations</Link>
        </Button>
        {!signedIn && instance.data?.registration_enabled && (
          <Button asChild variant="outline">
            <Link href="/register">Create account</Link>
          </Button>
        )}
        <Button asChild variant="outline">
          <Link href={signedIn ? "/dashboard" : "/login"}>
            {signedIn ? "Open workspace" : "Sign in"}
          </Link>
        </Button>
      </nav>
    </header>
  );
}
