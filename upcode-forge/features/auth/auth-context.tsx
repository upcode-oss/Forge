"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/services/api";
import type { User } from "@/types/api";
import { ErrorState, Loading } from "@/components/states";

const AuthContext = createContext<User | null>(null);
const AuthUpdateContext = createContext<Dispatch<
  SetStateAction<User | null>
> | null>(null);
export function AuthProvider({
  children,
  optional = false,
}: {
  children: React.ReactNode;
  optional?: boolean;
}) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let active = true;
    api<{ completed: boolean }>("/setup/status")
      .then(async (status) => {
        if (!active) return;
        if (!status.completed) {
          router.replace("/setup");
          return;
        }
        const value = await api<User>("/auth/me");
        if (active) setUser(value);
      })
      .catch((e) => {
        if (!active) return;
        if (e instanceof ApiError && e.status === 401) {
          if (!optional) router.replace("/login");
        } else if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, [router, optional]);
  if (error)
    return <ErrorState message={error} retry={() => location.reload()} />;
  if (!ready || (!optional && !user)) return <Loading />;
  return (
    <AuthContext.Provider value={user}>
      <AuthUpdateContext.Provider value={setUser}>
        {children}
      </AuthUpdateContext.Provider>
    </AuthContext.Provider>
  );
}
export function useOptionalAuth() {
  return useContext(AuthContext);
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
