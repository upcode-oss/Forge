"use client";

import Image from "next/image";
import { useState } from "react";
import type { Instance } from "@/types/api";

export function InstanceLogo({
  instance,
  width = 714,
  height = 631,
  className,
  sizes,
  priority = false,
}: {
  instance?: Pick<Instance, "name" | "logo_url"> | null;
  width?: number;
  height?: number;
  className?: string;
  sizes?: string;
  priority?: boolean;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  const custom =
    instance?.logo_url && instance.logo_url !== failed
      ? instance.logo_url
      : null;
  return (
    <Image
      src={custom ?? "/logo.png"}
      alt={instance?.name ?? "Upcode Forge"}
      width={width}
      height={height}
      className={className}
      sizes={sizes}
      priority={priority}
      unoptimized={Boolean(custom)}
      style={{ objectFit: "contain" }}
      onError={() => {
        if (custom) setFailed(custom);
      }}
    />
  );
}
