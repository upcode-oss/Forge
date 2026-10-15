"use client";
import {
  BarChart3,
  FolderGit2,
  GitPullRequest,
  Globe,
  LogOut,
  Menu,
  Moon,
  Settings,
  Sun,
  UserRound,
  Users,
  X,
} from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-context";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/services/api";
import { useToast } from "@/components/ui/toast";
import type { Instance } from "@/types/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const user = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { notify } = useToast();
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const { data: instance } = useResource<Instance>("/instance");
  useEffect(() => setMounted(true), []);
  const dark = mounted && resolvedTheme === "dark";
  const navigation = (href: string, label: string, Icon: typeof BarChart3) => (
    <Link
      key={href}
      href={href}
      onClick={() => setOpen(false)}
      className={`nav-item ${pathname.startsWith(href) ? "active" : ""}`}
    >
      <Icon />
      {label}
    </Link>
  );
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      router.replace("/login");
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }
  return (
    <div className="app-layout">
      {open && (
        <div
          className="sidebar-scrim"
          onClick={() => setOpen(false)}
          aria-hidden
        />
      )}
      <aside className={`sidebar upcode-forge-sidebar ${open ? "open" : ""}`}>
        <div className="sidebar-brand">
          <Link href="/dashboard" aria-label="Forge dashboard">
            <Image
              src="/logo.png"
              alt="Upcode Forge"
              width={210}
              height={66}
              priority
            />
          </Link>
          <div className="sidebar-brand-copy">
            <span>{instance?.name ?? "Upcode Forge"} · v0.1.0</span>
          </div>
          <Button
            className="mobile-menu sidebar-close"
            variant="ghost"
            size="icon"
            onClick={() => setOpen(false)}
            aria-label="Close navigation"
          >
            <X />
          </Button>
        </div>
        <nav className="sidebar-nav" aria-label="Primary navigation">
          <div className="nav-category">Workspace</div>
          {navigation("/dashboard", "Dashboard", BarChart3)}
          {navigation("/repositories", "Repositories", FolderGit2)}
          {user.is_admin && (
            <>
              <div className="nav-category">Administration</div>
              {navigation("/users", "Users", Users)}
              {navigation("/settings", "Organization & System", Settings)}
            </>
          )}
          <div className="nav-category">Account</div>
          {navigation(`/u/${user.username}`, "Public profile", Globe)}
          {navigation("/profile", "Profile & Access Tokens", UserRound)}
          <div className="sidebar-note">
            <GitPullRequest />
            <p>
              Your code. Your infrastructure.
              <br />
              <span className="muted">Built for collaboration.</span>
            </p>
          </div>
        </nav>
        <div className="sidebar-footer">
          <button
            className="theme-switch"
            role="switch"
            aria-checked={dark}
            aria-label={`Switch to ${dark ? "light" : "dark"} mode`}
            data-theme={dark ? "dark" : "light"}
            disabled={!mounted}
            onClick={() => setTheme(dark ? "light" : "dark")}
          >
            <span className="theme-switch-thumb" aria-hidden />
            <span className={`theme-switch-option ${!dark ? "active" : ""}`}>
              <Sun />
              Light
            </span>
            <span className={`theme-switch-option ${dark ? "active" : ""}`}>
              <Moon />
              Dark
            </span>
          </button>
          <div className="split">
            <Link href={`/u/${user.username}`} className="user-chip">
              <div className="avatar">
                {user.display_name.slice(0, 2).toUpperCase()}
              </div>
              <div>
                <strong>{user.display_name}</strong>
                <span>@{user.username}</span>
              </div>
            </Link>
            <Button
              variant="ghost"
              size="icon"
              onClick={logout}
              aria-label="Log out"
            >
              <LogOut />
            </Button>
          </div>
        </div>
      </aside>
      <div className="app-content">
        <main className="main-content">
          <div className="page-container">
            <Button
              className="mobile-menu mobile-navigation-trigger"
              variant="outline"
              size="icon"
              onClick={() => setOpen(true)}
              aria-label="Open navigation"
            >
              <Menu />
            </Button>
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
