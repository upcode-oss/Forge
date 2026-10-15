"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/services/api";
import type { User } from "@/types/api";
import { ErrorState, Loading } from "@/components/states";

const AuthContext = createContext<User | null>(null);
const AuthUpdateContext = createContext<((user: User) => void) | null>(null);
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<{ completed: boolean }>("/setup/status")
      .then(async (status) => {
        if (!status.completed) {
          router.replace("/setup");
          return;
        }
        const value = await api<User>("/auth/me");
        if (active) setUser(value);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace("/login");
        else if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [router]);
  if (error)
    return <ErrorState message={error} retry={() => location.reload()} />;
  if (!user) return <Loading />;
  return (
    <AuthContext.Provider value={user}>
      <AuthUpdateContext.Provider value={setUser}>{children}</AuthUpdateContext.Provider>
    </AuthContext.Provider>
  );
}
export function useAuth() {
  const user = useContext(AuthContext);
  if (!user) throw new Error("Missing auth provider");
  return user;
}
export function useUpdateAuth() {
  const update = useContext(AuthUpdateContext);
  if (!update) throw new Error("Missing auth provider");
  return update;
}
