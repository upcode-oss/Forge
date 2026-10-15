"use client";

import { FormEvent, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api, json } from "@/services/api";
import type {
  Organization,
  OrganizationSummary,
  SocialLink,
} from "@/types/api";

export function OrganizationForm({
  organization,
  onSaved,
}: {
  organization?: Organization;
  onSaved: (organization: OrganizationSummary) => void;
}) {
  const [links, setLinks] = useState<SocialLink[]>(
    organization?.social_links ?? [],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canChangeVisibility = !organization || organization.role === "owner";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    setError("");
    try {
      const result = await api<OrganizationSummary>(
        organization ? `/organizations/${organization.slug}` : "/organizations",
        {
          method: organization ? "PUT" : "POST",
          body: json({
            ...values,
            contact_email: values.contact_email || null,
            social_links: links,
            visibility: canChangeVisibility
              ? values.visibility
              : organization?.visibility,
          }),
        },
      );
      onSaved(result);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function changeLink(index: number, key: keyof SocialLink, value: string) {
    setLinks((items) =>
      items.map((item, i) => (i === index ? { ...item, [key]: value } : item)),
    );
  }
  return (
    <form onSubmit={submit}>
      <fieldset className="profile-fields form-grid" disabled={busy}>
        {!organization && (
          <Field
            label="URL name"
            hint="Permanent URL name. Lowercase letters, numbers, underscores and hyphens; start with a letter."
          >
            <Input
              name="slug"
              required
              pattern="[a-z][a-z0-9_-]{0,49}"
              maxLength={50}
              placeholder="your-team"
            />
          </Field>
        )}
        <Field label="Organization name">
          <Input
            name="name"
            required
            maxLength={100}
            defaultValue={organization?.name}
            placeholder="Your team"
          />
        </Field>
        <Field label="Description">
          <Textarea
            name="description"
            maxLength={500}
            defaultValue={organization?.description}
            placeholder="What does your organization do?"
          />
        </Field>
        <Field
          label="Visibility"
          hint={
            canChangeVisibility
              ? "Private organizations are visible only to members. Public organizations appear in search and on member profiles."
              : "Only Owners can change visibility."
          }
        >
          <Select
            name="visibility"
            defaultValue={organization?.visibility ?? "private"}
            disabled={!canChangeVisibility}
          >
            <option value="private">Private — members only</option>
            <option value="public">Public — visible to everyone</option>
          </Select>
        </Field>
        <Field
          label="Contact email"
          hint="Shown on the organization profile to people who can view it."
        >
          <Input
            name="contact_email"
            type="email"
            maxLength={254}
            defaultValue={organization?.contact_email ?? ""}
            placeholder="hello@example.com"
          />
        </Field>
        <div className="social-editor">
          <div className="split">
            <strong>Social links</strong>
            <span className="muted small">{links.length} / 10</span>
          </div>
          {links.map((link, index) => (
            <div className="social-editor-row" key={index}>
              <Field label={`Link ${index + 1} name`}>
                <Input
                  required
                  maxLength={40}
                  value={link.label}
                  onChange={(e) => changeLink(index, "label", e.target.value)}
                  placeholder="GitHub"
                />
              </Field>
              <Field label={`Link ${index + 1} URL`}>
                <Input
                  required
                  type="url"
                  maxLength={500}
                  value={link.url}
                  onChange={(e) => changeLink(index, "url", e.target.value)}
                  placeholder="https://github.com/your-team"
                />
              </Field>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remove social link ${index + 1}`}
                onClick={() =>
                  setLinks((items) => items.filter((_, i) => i !== index))
                }
              >
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={links.length >= 10}
            onClick={() =>
              setLinks((items) => [...items, { label: "", url: "" }])
            }
          >
            <Plus /> Add social link
          </Button>
        </div>
      </fieldset>
      {error && (
        <p role="alert" className="field-error">
          {error}
        </p>
      )}
      <div className="form-actions">
        <Button loading={busy}>
          {organization ? "Save organization" : "Create organization"}
        </Button>
      </div>
    </form>
  );
}
