"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { ArrowUpRight, Plus, Trash2 } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/form";
import { useToast } from "@/components/ui/toast";
import { ErrorState, Loading } from "@/components/states";
import { useAuth, useUpdateAuth } from "@/features/auth/auth-context";
import { useResource } from "@/hooks/use-resource";
import { api, json } from "@/services/api";
import type { ProfileFields, SocialLink } from "@/types/api";

function ProfileForm({ profile, saved }: { profile: ProfileFields; saved: () => void }) {
  const user = useAuth();
  const updateAuth = useUpdateAuth();
  const { notify } = useToast();
  const [links, setLinks] = useState<SocialLink[]>(profile.social_links);
  const [busy, setBusy] = useState(false);
  function changeLink(index: number, key: keyof SocialLink, value: string) {
    setLinks((items) => items.map((item, i) => i === index ? { ...item, [key]: value } : item));
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    try {
      const updated = await api<ProfileFields>("/profile", {
        method: "PUT",
        body: json({ ...values, public_email: values.public_email || null, social_links: links }),
      });
      updateAuth({ ...user, display_name: updated.display_name });
      notify("Public profile saved");
      saved();
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <fieldset className="profile-fields form-grid" disabled={busy}>
        <Field label="Display name"><Input name="display_name" required maxLength={100} defaultValue={profile.display_name} autoComplete="name" /></Field>
        <Field label="Bio" hint="A little about you. Up to 500 characters."><Textarea name="bio" maxLength={500} defaultValue={profile.bio} placeholder="What do you enjoy building?" /></Field>
        <div className="form-grid two">
          <Field label="Workplace / company"><Input name="company" maxLength={100} defaultValue={profile.company} autoComplete="organization" /></Field>
          <Field label="Location"><Input name="location" maxLength={100} defaultValue={profile.location} placeholder="Vienna, Austria" /></Field>
        </div>
        <Field label="Public email" hint="Visible to everyone. Leave blank to hide it. Your account email stays private."><Input name="public_email" type="email" maxLength={254} defaultValue={profile.public_email ?? ""} placeholder="hello@example.com" /></Field>
        <Field label="Website"><Input name="website" type="url" maxLength={500} defaultValue={profile.website} placeholder="https://your-website.com" /></Field>
        <div className="social-editor">
          <div className="split"><strong>Social links</strong><span className="muted small">{links.length} / 10</span></div>
          <p className="muted small">Connect GitHub, GitLab, LinkedIn, Mastodon or any other public profile.</p>
          {links.map((link, index) => (
            <div className="social-editor-row" key={index}>
              <Field label={`Link ${index + 1} name`}><Input required maxLength={40} list="social-link-names" value={link.label} onChange={(event) => changeLink(index, "label", event.target.value)} placeholder="GitHub" /></Field>
              <Field label={`Link ${index + 1} URL`}><Input type="url" required maxLength={500} value={link.url} onChange={(event) => changeLink(index, "url", event.target.value)} placeholder="https://github.com/you" /></Field>
              <Button type="button" size="icon" variant="ghost" aria-label={`Remove social link ${index + 1}`} onClick={() => setLinks((items) => items.filter((_, i) => i !== index))}><Trash2 /></Button>
            </div>
          ))}
          <datalist id="social-link-names">{["GitHub", "GitLab", "LinkedIn", "Mastodon", "Bluesky", "YouTube", "Instagram"].map((label) => <option key={label} value={label} />)}</datalist>
          <Button type="button" size="sm" variant="outline" disabled={links.length >= 10} onClick={() => setLinks((items) => [...items, { label: "", url: "" }])}><Plus /> Add social link</Button>
        </div>
      </fieldset>
      <div className="form-actions"><Button loading={busy}>Save public profile</Button></div>
    </form>
  );
}

export function ProfileEditor() {
  const user = useAuth();
  const profile = useResource<ProfileFields>("/profile");
  return (
    <Card>
      <CardHeader title="Public profile" description="Tell people who you are. These details are visible without signing in."
        action={<Button asChild variant="outline" size="sm"><Link href={`/u/${user.username}`}>View profile <ArrowUpRight /></Link></Button>} />
      {profile.loading ? <Loading /> : profile.error ? <ErrorState message={profile.error} retry={profile.reload} /> : profile.data && <ProfileForm profile={profile.data} saved={profile.reload} />}
    </Card>
  );
}
