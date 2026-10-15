"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { Trash2, Upload } from "lucide-react";
import { Avatar } from "@/components/avatar";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { useAuth, useUpdateAuth } from "@/features/auth/auth-context";
import { api } from "@/services/api";

export function AvatarUploader() {
  const user = useAuth();
  const updateAuth = useUpdateAuth();
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
      const result = await api<{ avatar_url: string }>("/profile/avatar", {
        method: "PUT",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      updateAuth((current) =>
        current ? { ...current, avatar_url: result.avatar_url } : current,
      );
      reset();
      notify("Profile picture updated");
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api("/profile/avatar", { method: "DELETE" });
      updateAuth((current) =>
        current ? { ...current, avatar_url: null } : current,
      );
      reset();
      notify("Profile picture removed");
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="avatar-editor" onSubmit={save}>
      <Avatar
        name={user.display_name}
        src={preview ?? user.avatar_url}
        className="profile-editor-avatar"
      />
      <div className="avatar-editor-fields">
        <Field
          label="Profile picture"
          hint="Visible on your public profile. PNG, JPEG or WebP, up to 5 MiB. Images are cropped to a square."
        >
          <Input
            ref={input}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={select}
            disabled={busy}
          />
        </Field>
        <div className="avatar-editor-actions">
          <Button size="sm" loading={busy} disabled={!file}>
            <Upload /> {user.avatar_url ? "Replace picture" : "Upload picture"}
          </Button>
          {user.avatar_url && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => void remove()}
            >
              <Trash2 /> Remove picture
            </Button>
          )}
          {file && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={reset}
            >
              Cancel
            </Button>
          )}
        </div>
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </form>
  );
}
