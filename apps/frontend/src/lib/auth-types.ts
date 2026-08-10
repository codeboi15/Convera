import type { Role } from "@/lib/types";

export interface User {
  id: string;
  email: string;
  name?: string | null;
}

export interface WorkspaceMembership {
  id: string;
  name: string;
  slug: string;
  role: Role;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
  active_workspace_id?: string | null;
  workspaces: WorkspaceMembership[];
}

export interface MeResponse {
  user: User;
  active_workspace_id?: string | null;
  active_role?: Role | null;
  workspaces: WorkspaceMembership[];
}

export interface TeamMember {
  user_id: string;
  email: string;
  name?: string | null;
  role: Role;
  joined_at: string;
}

export interface WorkspaceSettings {
  id: string;
  name: string;
  slug: string;
  inbound_key: string;
  /** Address customers email (or forward their support address to). */
  inbound_address: string;
  support_email?: string | null;
  custom_domain?: string | null;
  custom_domain_verified: boolean;
}

export interface Invite {
  id: string;
  email: string;
  role: Role;
  accepted: boolean;
  expires_at: string;
  created_at: string;
  invite_url?: string | null;
}
