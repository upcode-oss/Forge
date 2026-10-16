"use client";

import { useEffect } from "react";
import { useResource } from "@/hooks/use-resource";
import type { Instance } from "@/types/api";

export function instanceUpdated() {
  window.dispatchEvent(new Event("instance-updated"));
}

export function useInstance(enabled = true) {
  const resource = useResource<Instance>(enabled ? "/instance" : null);
  const { reload } = resource;
  useEffect(() => {
    if (!enabled) return;
    window.addEventListener("instance-updated", reload);
    return () => window.removeEventListener("instance-updated", reload);
  }, [enabled, reload]);
  return resource;
}
