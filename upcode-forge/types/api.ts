export type User = {
  id: number;
  username: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
};
export type SocialLink = { label: string; url: string };
export type ProfileFields = {
  username: string;
  display_name: string;
  avatar_url: string | null;
  bio: string;
  company: string;
  location: string;
  website: string;
  public_email: string | null;
  social_links: SocialLink[];
  created_at: string;
};
export type ProfileActivity = {
  year: number;
  available_years: number[];
  days: { date: string; count: number; private_count: number }[];
  totals: {
    commits: number;
    repositories: number;
    issues: number;
    pulls: number;
    comments: number;
  };
  total: number;
  private_total: number;
  longest_streak: number;
  incomplete: boolean;
};
export type PublicProfile = ProfileFields & {
  repository_count: number;
  repositories: Repository[];
  activity: ProfileActivity;
};
export type Instance = {
  name: string;
  public_url: string;
  default_branch: string;
  version: string;
};
export type Repository = {
  id: number;
  name: string;
  owner: string;
  description: string;
  visibility: "public" | "private";
  default_branch: string;
  clone_url: string;
  ssh_clone_url: string | null;
  role: "read" | "write" | "maintain";
  created_at: string;
};
export type SSHKey = {
  id: number;
  name: string;
  public_key: string;
  fingerprint: string;
  scope: "read" | "write";
  created_at: string;
  last_used_at: string | null;
};
export type SSHStatus = {
  enabled: boolean;
  host: string;
  port: number;
  username: "git";
  host_fingerprint: string | null;
};
export type Ticket = {
  id: number;
  kind: "issue" | "pull";
  title: string;
  body: string;
  state: "open" | "closed" | "merged";
  author: string;
  source_branch: string | null;
  target_branch: string | null;
  created_at: string;
  comments?: Comment[];
};
export type Comment = {
  id: number;
  author: string;
  body: string;
  created_at: string;
};
export type Commit = {
  sha: string;
  subject: string;
  author: string;
  date: string;
};
export type TreeEntry = {
  name: string;
  kind: string;
  mode: string;
  oid: string;
};
export type SMTP = {
  host: string;
  port: number;
  username: string;
  password: string;
  encryption: "starttls" | "tls";
  from_address: string | null;
  has_password?: boolean;
};
