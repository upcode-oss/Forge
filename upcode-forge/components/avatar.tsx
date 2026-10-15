"use client";

import Image from "next/image";
import { useState } from "react";
import { cn } from "@/lib/utils";

export function Avatar({
  name,
  src,
  className,
}: {
  name: string;
  src?: string | null;
  className?: string;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  return (
    <span className={cn("avatar", className)} aria-hidden="true">
      {src && src !== failed ? (
        <Image
          src={src}
          alt=""
          width={256}
          height={256}
          unoptimized
          className="avatar-picture"
          onError={() => setFailed(src)}
        />
      ) : (
        name.slice(0, 2).toUpperCase()
      )}
    </span>
  );
}
