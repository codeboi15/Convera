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

export type ArticleStatus = "draft" | "published";

export interface KBCategory {
  id: string;
  name: string;
  slug: string;
  position: number;
  article_count: number;
}

export interface KBArticle {
  id: string;
  title: string;
  slug: string;
  body_html: string;
  body_text: string;
  status: ArticleStatus;
  category_id?: string | null;
  category_name?: string | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
}

/** Compact shape used by search results and widget suggestions. */
export interface ArticleSummary {
  id: string;
  title: string;
  slug: string;
  excerpt: string;
  category_name?: string | null;
}

export interface PublicCategory {
  name: string;
  slug: string;
  articles: ArticleSummary[];
}

export interface PublicKnowledgeBase {
  workspace_name: string;
  workspace_slug: string;
  categories: PublicCategory[];
  uncategorized: ArticleSummary[];
}

export interface PublicArticle {
  id: string;
  title: string;
  slug: string;
  body_html: string;
  category_name?: string | null;
  published_at?: string | null;
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
