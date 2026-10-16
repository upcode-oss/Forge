"use client";

import Image from "next/image";
import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { RotateCcw, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { instanceUpdated } from "@/hooks/use-instance";
import { api } from "@/services/api";
import type { Instance } from "@/types/api";

export function InstanceLogoUploader({ instance }: { instance: Instance }) {
  const { notify } = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );

  function reset() {
    setFile(null);
    setPreview(null);
    if (input.current) input.current.value = "";
  }

  function select(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
    setFile(null);
    setPreview(null);
    setError("");
    if (!chosen) return;
    if (chosen.size > 5 * 1024 * 1024) {
      setError("Choose an image no larger than 5 MiB.");
      return;
    }
    if (
      chosen.type
        ? !["image/png", "image/jpeg", "image/webp"].includes(chosen.type)
        : !/\.(png|jpe?g|webp)$/i.test(chosen.name)
    ) {
      setError("Choose a PNG, JPEG or WebP image.");
      return;
    }
    setFile(chosen);
    setPreview(URL.createObjectURL(chosen));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await api("/instance/logo", {
        method: "PUT",
        body: file,
        headers: { "Content-Type": file.type || "application/octet-stream" },
      });
      reset();
      instanceUpdated();
      notify("Instance logo updated");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api("/instance/logo", { method: "DELETE" });
      reset();
      instanceUpdated();
      notify("Default Forge logo restored");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form-grid" onSubmit={save}>
      <div className="organization-settings-logo">
        <Image
          src={preview ?? instance.logo_url ?? "/logo.png"}
          alt={preview ? "Selected logo preview" : `${instance.name} logo`}
          width={72}
          height={72}
          unoptimized
        />
        <div>
          <strong>Instance logo</strong>
          <p className="muted small">
            {file
              ? file.name
              : instance.logo_url
                ? "Custom logo"
                : "Default Forge logo"}
          </p>
        </div>
      </div>
      <Field
        label="Logo image"
        hint="PNG, JPEG or WebP, up to 5 MiB and 16 million pixels. Aspect ratio and transparency are preserved. Used in navigation, sign-in and registration."
      >
        <Input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={select}
          disabled={busy}
        />
      </Field>
      <div className="form-actions">
        <Button loading={busy} disabled={!file}>
          <Upload />
          {instance.logo_url ? "Replace logo" : "Upload logo"}
        </Button>
        {instance.logo_url ? (
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => void remove()}
          >
            <RotateCcw />
            Use default logo
          </Button>
        ) : null}
        {file ? (
          <Button
            type="button"
            variant="ghost"
            disabled={busy}
            onClick={() => {
              reset();
              setError("");
            }}
          >
            Cancel
          </Button>
        ) : null}
      </div>
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}
    </form>
  );
}
