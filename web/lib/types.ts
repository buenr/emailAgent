/**
 * Shared API response types for the Email Tagging UI.
 *
 * Types that represent API responses are centralized here.
 * Page-specific UI state types (e.g. local form state) remain inline in each page.
 */

/* ------------------------------------------------------------------ */
/*  Generic paginated response                                         */
/* ------------------------------------------------------------------ */

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

/* ------------------------------------------------------------------ */
/*  Named entity (shared by prompts, classification-sets, app-models) */
/* ------------------------------------------------------------------ */

export type Named = { id: number; name: string };

/* ------------------------------------------------------------------ */
/*  Inbox summary (used by prompts page, results page)                  */
/* ------------------------------------------------------------------ */

export type InboxPick = { id: number; mailbox_id: string };

/* ------------------------------------------------------------------ */
/*  Dashboard types                                                    */
/* ------------------------------------------------------------------ */

export type FleetRow = {
  id: number;
  mailbox_id: string;
  polling_interval_minutes: number;
  is_active: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  emails_processed_24h: number;
  token_spend_24h: number;
  health_ok: boolean;
  last_run_status?: string | null;
  last_error_message?: string | null;
  prompt_name?: string;
  classification_set_name?: string;
};

export type FleetPage = PaginatedResponse<FleetRow>;

export type TokenTrendPoint = {
  date: string;
  total_tokens: number;
};

export type ClassificationBreakdown = Record<string, number>;

export type RunVolumePoint = {
  date: string;
  run_count: number;
  message_count: number;
};

/* ------------------------------------------------------------------ */
/*  Prompt template types                                              */
/* ------------------------------------------------------------------ */

export type Template = {
  id: number;
  name: string;
  body: string;
  created_at: string;
  updated_at: string;
};

export type TestPromptResult = {
  model_json: Record<string, unknown> | null;
  category_resolved: string;
  usage: { prompt_token_count: number; candidates_token_count: number };
  error: string | null;
  warning: string | null;
  raw_text: string | null;
};

/* ------------------------------------------------------------------ */
/*  Classification set types                                           */
/* ------------------------------------------------------------------ */

export type SetRow = {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
};

export type TaxRow = { name: string; description: string };

export type ClassificationSetDetail = SetRow & { categories: TaxRow[] };

/* ------------------------------------------------------------------ */
/*  App model types                                                    */
/* ------------------------------------------------------------------ */

export type AppModel = {
  id: number;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Subset used in dropdowns (e.g. inbox model selector). */
export type AppModelRow = { id: number; name: string };

export type AgentApiConfig = {
  name: string;
  api_url: string;
  api_key: string;
};

/* ------------------------------------------------------------------ */
/*  Inbox types                                                        */
/* ------------------------------------------------------------------ */

export type TimeWindowMode = "local_today" | "rolling_hours" | "since_last_run";
export type SubjectKeywordMode = "all" | "any";
export type AttachmentFilter = "any" | "yes" | "no";

export type FetchFilter = {
  unread_only: boolean;
  time_window_mode: TimeWindowMode;
  rolling_hours: number | null;
  sender_allowlist: string[];
  sender_denylist: string[];
  subject_keywords: string[];
  subject_keyword_mode: SubjectKeywordMode;
  body_keywords: string[];
  importance_levels: string[];
  has_attachments: AttachmentFilter;
  category_include_any: string[];
  category_exclude_any: string[];
};

export type SubjectRuleRow = { pattern: string; category: string };

export type Inbox = {
  id: number;
  mailbox_id: string;
  prompt_template_id: number;
  classification_set_id: number;
  app_model_id?: number | null;
  app_model_name?: string;
  timezone: string;
  mail_folder: string;
  max_messages_per_run: number | null;
  patch_max_workers: number;
  polling_interval_minutes?: number;
  is_active?: boolean;
  graph_write_back_enabled?: boolean;
  subject_classify_enabled?: boolean;
  subject_classify_rules?: SubjectRuleRow[];
  prompt_name?: string;
  classification_set_name?: string;
  fetch_filter?: FetchFilter | null;
};

/* ------------------------------------------------------------------ */
/*  Run log / classification result types                               */
/* ------------------------------------------------------------------ */

export type RunLogRow = {
  id: number;
  status: string;
  fetched_count: number;
  classified_count: number;
  tagged_count: number;
  failures: number;
  latency_ms: number;
  total_tokens_used: number | null;
  error_message: string | null;
  created_at: string;
};

export type ClassificationRow = {
  id: number;
  run_log_id: number;
  email_id: string;
  subject: string;
  sender: string;
  category: string;
  received_at: string;
  created_at: string;
};

export type ClassificationsResponse = PaginatedResponse<ClassificationRow>;
