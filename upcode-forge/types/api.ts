export type User = {
  id: number;
  username: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
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
  role: "read" | "write" | "maintain";
  created_at: string;
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
