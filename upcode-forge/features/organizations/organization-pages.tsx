"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  ExternalLink,
  Globe,
  Link2,
  LockKeyhole,
  Mail,
  Settings,
  Users,
} from "lucide-react";
import { Avatar } from "@/components/avatar";
import { PageHeader } from "@/components/page-header";
import { ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/features/auth/auth-context";
import { AvatarUpload } from "@/features/profile/avatar-uploader";
import { useResource } from "@/hooks/use-resource";
import { api } from "@/services/api";
import type { Organization } from "@/types/api";
import { OrganizationForm } from "./organization-form";
import { OrganizationPublicHeader } from "./organization-list";
import { OrganizationMembers } from "./organization-members";

export function CreateOrganization() {
  const router = useRouter();
  return (
    <>
      <PageHeader
        title="Create an organization"
        description="Bring your team together. You become the first Owner."
        actions={
          <Button asChild variant="outline">
            <Link href="/organizations">Back to organizations</Link>
          </Button>
        }
      />
      <Card>
        <OrganizationForm
          onSaved={(organization) =>
            router.push(`/organizations/${organization.slug}`)
          }
        />
      </Card>
    </>
  );
}

function OrganizationIdentity({
  organization,
}: {
  organization: Organization;
}) {
  return (
    <Card className="public-profile-identity">
      <Avatar
        name={organization.name}
        src={organization.avatar_url}
        className="public-profile-avatar"
      />
      <h1>{organization.name}</h1>
      <p className="muted">@{organization.slug}</p>
      <span className="badge">
        {organization.visibility === "private" ? <LockKeyhole /> : <Globe />}
        {organization.visibility}
      </span>
      {organization.description && (
        <p className="public-profile-bio">{organization.description}</p>
      )}
      <ul className="public-profile-facts">
        <li>
          <Users />
          <span>
            {organization.member_count}{" "}
            {organization.member_count === 1 ? "member" : "members"}
          </span>
        </li>
        {organization.contact_email && (
          <li>
            <Mail />
            <a href={`mailto:${organization.contact_email}`}>
              {organization.contact_email}
            </a>
          </li>
        )}
      </ul>
      {!!organization.social_links.length && (
        <div className="public-profile-socials">
          {organization.social_links.map((link, i) => (
            <a
              key={i}
              href={link.url}
              target="_blank"
              rel="noopener noreferrer me"
            >
              <Link2 />
              <span>{link.label}</span>
              <ExternalLink />
            </a>
          ))}
        </div>
      )}
      {organization.role && (
        <Button asChild variant="outline" size="sm">
          <Link href={`/organizations/${organization.slug}`}>
            <Settings /> Your membership
          </Link>
        </Button>
      )}
    </Card>
  );
}

export function PublicOrganization({ slug }: { slug: string }) {
  const resource = useResource<Organization>(
    `/organizations/${encodeURIComponent(slug)}`,
  );
  return (
    <div className="public-profile-page">
      <OrganizationPublicHeader />
      <main className="public-profile-main">
        {resource.loading ? (
          <Loading />
        ) : resource.error ? (
          <ErrorState message={resource.error} retry={resource.reload} />
        ) : (
          resource.data && (
            <div className="public-profile-grid">
              <aside>
                <OrganizationIdentity organization={resource.data} />
              </aside>
              <OrganizationMembers slug={resource.data.slug} />
            </div>
          )
        )}
      </main>
    </div>
  );
}

function OrganizationSettings({
  organization,
  reload,
}: {
  organization: Organization;
  reload: () => void;
}) {
  const user = useAuth();
  const router = useRouter();
  const { notify } = useToast();
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [avatarUrl, setAvatarUrl] = useState(organization.avatar_url);
  const editable =
    organization.role === "owner" || organization.role === "maintainer";
  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api(`/organizations/${organization.slug}`, { method: "DELETE" });
      router.push("/organizations");
      notify("Organization deleted");
    } catch (error) {
      setDeleting(false);
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack">
      {editable ? (
        <Card>
          <CardHeader
            title="Organization profile"
            description={`Your role: ${organization.role === "owner" ? "Owner" : "Maintainer"}. Profile details follow the organization's visibility.`}
          />
          <AvatarUpload
            name={organization.name}
            avatarUrl={avatarUrl}
            endpoint={`/organizations/${organization.slug}/avatar`}
            hint="PNG, JPEG or WebP, up to 5 MiB. Private organization pictures are visible only to members."
            onSaved={setAvatarUrl}
          />
          <OrganizationForm
            organization={organization}
            onSaved={() => {
              notify("Organization saved");
              reload();
            }}
          />
        </Card>
      ) : (
        <Card>
          <CardHeader
            title="Your membership"
            description="Readers can view this organization and its members. Ask an Owner to change your role."
          />
          <p className="muted">Your role: Reader</p>
        </Card>
      )}
      <OrganizationMembers
        slug={organization.slug}
        role={organization.role}
        username={user.username}
        onLeave={() => router.push("/organizations")}
      />
      {organization.role === "owner" && (
        <Card>
          <CardHeader
            title="Delete organization"
            description="Permanently removes this organization, its profile picture and all memberships."
          />
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <Button variant="destructive" onClick={() => setDeleting(true)}>
            Delete organization
          </Button>
          <ConfirmDialog
            open={deleting}
            onOpenChange={(open) => {
              if (!busy) setDeleting(open);
            }}
            title={`Delete ${organization.name}?`}
            description="This permanently deletes the organization and all its memberships. Member accounts and their repositories are kept."
            loading={busy}
            onConfirm={() => void remove()}
          />
        </Card>
      )}
    </div>
  );
}

export function OrganizationWorkspace({ slug }: { slug: string }) {
  const resource = useResource<Organization>(
    `/organizations/${encodeURIComponent(slug)}`,
  );
  return (
    <>
      <PageHeader
        title={resource.data?.name ?? "Organization"}
        description={
          resource.data
            ? `@${resource.data.slug} · ${resource.data.visibility}`
            : "Organization settings and members"
        }
        actions={
          <Button asChild variant="outline">
            <Link href={`/o/${encodeURIComponent(slug)}`}>
              View profile <ExternalLink />
            </Link>
          </Button>
        }
      />
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState message={resource.error} retry={resource.reload} />
      ) : (
        resource.data &&
        (resource.data.role ? (
          <OrganizationSettings
            organization={resource.data}
            reload={resource.reload}
          />
        ) : (
          <Card>
            <p>
              You are not a member of this organization. Contact an Owner or
              Maintainer to join.
            </p>
            <Button asChild variant="outline">
              <Link href={`/o/${resource.data.slug}`}>View organization</Link>
            </Button>
          </Card>
        ))
      )}
    </>
  );
}
