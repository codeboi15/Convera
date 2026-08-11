export type SenderType = "contact" | "agent" | "system";
export type Channel = "chat" | "email";
export type ConversationStatus = "open" | "snoozed" | "resolved";
export type Role = "admin" | "agent";

export interface Message {
  id: string;
  conversation_id: string;
  seq: number;
  sender_type: SenderType;
  sender_user_id?: string | null;
  sender_contact_id?: string | null;
  body: string;
  html?: string | null;
  read_at?: string | null;
  created_at: string;
}

export interface Contact {
  id: string;
  name?: string | null;
  email?: string | null;
  last_seen_at?: string | null;
}

export interface Assignee {
  id: string;
  name?: string | null;
  email: string;
}

export interface Conversation {
  id: string;
  channel: Channel;
  status: ConversationStatus;
  subject?: string | null;
  contact: Contact;
  assignee?: Assignee | null;
  last_message_at?: string | null;
  snoozed_until?: string | null;
  message_count: number;
  ai_summary?: string | null;
  ai_summary_updated_at?: string | null;
  created_at: string;
  last_message_preview?: string | null;
  unread_count: number;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface ConversationList {
  items: Conversation[];
  total: number;
  limit: number;
  offset: number;
}

export interface WidgetSession {
  token: string;
  visitor_id: string;
  workspace_id: string;
  workspace_name: string;
  contact_id: string;
  conversation_id: string;
  messages: Message[];
  agents_online: boolean;
}
