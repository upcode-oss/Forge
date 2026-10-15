"use client";

import { useState } from "react";
import { Field, Input, Select } from "@/components/ui/form";
import { useResource } from "@/hooks/use-resource";

export type RepositoryOrganization = {
  slug: string;
  name: string;
  visibility: "public" | "private";
};
export type RepositoryOwners = {
  username: string;
  organizations: RepositoryOrganization[];
};

export function RepositoryOwnerFields({
  organization,
  disabled = false,
}: {
  organization?: RepositoryOrganization;
  disabled?: boolean;
}) {
  const owners = useResource<RepositoryOwners>(
    organization ? null : "/repository-owners",
  );
  const [slug, setSlug] = useState("");
  const selected =
    organization ??
    owners.data?.organizations.find((item) => item.slug === slug);
  const privateOrganization = selected?.visibility === "private";
  return (
    <>
      <Field
        label="Owner"
        hint={
          organization
            ? "This repository belongs to the organization."
            : "Choose your account or an organization you own or maintain."
        }
      >
        {organization ? (
          <>
            <Input readOnly value={organization.name} />
            <input
              type="hidden"
              name="organization"
              value={organization.slug}
            />
          </>
        ) : (
          <Select
            name="organization"
            value={slug}
            disabled={disabled}
            onChange={(event) => setSlug(event.target.value)}
          >
            <option value="">
              {owners.data
                ? `${owners.data.username} (your account)`
                : "Your account"}
            </option>
            {owners.data?.organizations.map((item) => (
              <option key={item.slug} value={item.slug}>
                {item.name} (@{item.slug})
              </option>
            ))}
          </Select>
        )}
      </Field>
      {!organization && owners.loading && (
        <p className="muted small" role="status">
          Loading organization owners…
        </p>
      )}
      {!organization && owners.error && (
        <p className="field-error" role="alert">
          {owners.error}{" "}
          <button type="button" className="text-link" onClick={owners.reload}>
            Retry loading organizations
          </button>
        </p>
      )}
      <Field
        label="Visibility"
        hint={
          privateOrganization
            ? "Repositories in private organizations are visible only to organization members."
            : "Public repositories can be cloned by anyone."
        }
      >
        <Select
          key={selected?.slug ?? "personal"}
          name="visibility"
          defaultValue="private"
          disabled={disabled}
        >
          <option value="private">Private — members only</option>
          {!privateOrganization && (
            <option value="public">Public — anyone can clone</option>
          )}
        </Select>
      </Field>
    </>
  );
}
