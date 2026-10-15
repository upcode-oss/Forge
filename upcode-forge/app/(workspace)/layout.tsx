import { AuthProvider } from "@/features/auth/auth-context";
import { AppShell } from "@/components/app-shell";
export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  );
}
