"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import { Trash2 } from "lucide-react";
import { Avatar } from "@/components/avatar";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { useAuth, useUpdateAuth } from "@/features/auth/auth-context";
import { api } from "@/services/api";

export function AvatarUploader() {
  const user = useAuth();
  const updateAuth = useUpdateAuth();
  return (
    <AvatarUpload
      name={user.display_name}
      avatarUrl={user.avatar_url}
      endpoint="/profile/avatar"
      hint="Visible on your public profile. PNG, JPEG or WebP, up to 5 MiB. Images are cropped to a square."
      onSaved={(avatar_url) =>
        updateAuth((current) =>
          current ? { ...current, avatar_url } : current,
        )
      }
    />
  );
}

export function AvatarUpload({
  name,
  avatarUrl,
  endpoint,
  hint,
  onSaved,
}: {
  name: string;
  avatarUrl: string | null;
  endpoint: string;
  hint: string;
  onSaved: (url: string | null) => void;
}) {
  const { notify } = useToast();
  const input = useRef<HTMLInputElement>(null);
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
    setPreview(null);
    if (input.current) input.current.value = "";
  }
  function select(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
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
    setPreview(URL.createObjectURL(chosen));
    void save(chosen);
  }
  async function save(file: File) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ avatar_url: string }>(endpoint, {
        method: "PUT",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      onSaved(result.avatar_url);
      reset();
      notify("Profile picture updated");
    } catch (error) {
      reset();
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api(endpoint, { method: "DELETE" });
      onSaved(null);
      reset();
      notify("Profile picture removed");
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="avatar-editor" aria-busy={busy}>
      <Avatar
        name={name}
        src={preview ?? avatarUrl}
        className="profile-editor-avatar"
      />
      <div className="avatar-editor-fields">
        <Field
          label="Profile picture"
          hint={`${hint} Pictures are saved automatically after selection.`}
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
          {busy && <p role="status">Saving profile picture…</p>}
          {avatarUrl && (
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
        </div>
        {error && (
          <p className="field-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
