"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";

export type CloneProtocol = "https" | "ssh";

export function CloneBar({
  httpsUrl,
  sshUrl,
  protocol,
  onProtocolChange,
}: {
  httpsUrl: string;
  sshUrl: string | null;
  protocol: CloneProtocol;
  onProtocolChange: (value: CloneProtocol) => void;
}) {
  const { notify } = useToast();
  const [copied, setCopied] = useState<string | null>(null);
  const selected = protocol === "ssh" && sshUrl ? "ssh" : "https";
  const url = selected === "ssh" ? sshUrl! : httpsUrl;
  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(url);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      notify("Select and copy the clone URL manually.", "error");
    }
  }
  return (
    <div className="clone-bar">
      <Select
        aria-label="Clone protocol"
        className="clone-protocol"
        value={selected}
        onChange={(event) =>
          onProtocolChange(event.target.value as CloneProtocol)
        }
      >
        <option value="https">HTTPS</option>
        {sshUrl && <option value="ssh">SSH</option>}
      </Select>
      <code>{url}</code>
      <Button variant="outline" size="sm" onClick={() => void copy()}>
        {copied === url ? <Check /> : <Copy />}
        {copied === url ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}
