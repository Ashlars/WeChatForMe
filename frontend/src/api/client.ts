const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  // Dashboard
  getDashboard: () => request<DashboardSummary>('/dashboard/summary'),

  // Contacts
  listContacts: (page = 1) => request<Paginated>(`/contacts?page=${page}`),
  getContact: (wxid: string) => request<Contact>(`/contacts/${wxid}`),
  deleteContact: (wxid: string) => request<{ deleted: boolean }>(`/contacts/${wxid}`, { method: 'DELETE' }),
  cleanupContacts: () => request<{ removed: any[]; removed_count: number }>('/contacts/cleanup', { method: 'POST' }),
  updateContact: (wxid: string, patch: Partial<Contact>) =>
    request<Contact>(`/contacts/${wxid}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  analyzeContact: (wxid: string) =>
    request<{ analysis_run_id: number; status: string }>(`/contacts/${wxid}/analyze`, { method: 'POST' }),

  // Groups
  listGroups: (page = 1) => request<Paginated>(`/groups?page=${page}`),
  getGroup: (id: string) => request<Group>(`/groups/${id}`),
  deleteGroup: (id: string) => request<{ deleted: boolean }>(`/groups/${id}`, { method: 'DELETE' }),
  updateGroup: (id: string, patch: Partial<Group>) =>
    request<Group>(`/groups/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  analyzeGroup: (id: string) =>
    request<{ analysis_run_id: number; status: string }>(`/groups/${id}/analyze`, { method: 'POST' }),

  // Rules
  getDefaultRule: () => request<Rule>('/rules/default'),
  putDefaultRule: (doc: object) => request<Rule>('/rules/default', { method: 'PUT', body: JSON.stringify({ document: doc }) }),
  getPrivateRule: (wxid: string) => request<Rule>(`/rules/private/${wxid}`).catch(() => null),
  putPrivateRule: (wxid: string, doc: object) =>
    request<Rule>(`/rules/private/${wxid}`, { method: 'PUT', body: JSON.stringify({ document: doc }) }),
  getGroupRule: (id: string) => request<Rule>(`/rules/group/${id}`).catch(() => null),
  putGroupRule: (id: string, doc: object) =>
    request<Rule>(`/rules/group/${id}`, { method: 'PUT', body: JSON.stringify({ document: doc }) }),

  // Analyses
  listAnalyses: (page = 1) => request<Paginated>(`/analysis-runs?page=${page}`),
  getAnalysis: (id: number) => request<AnalysisRun>(`/analysis-runs/${id}`),

  // Reviews
  listReviews: (page = 1, status?: string) => {
    let url = `/reviews?page=${page}`;
    if (status) url += `&status=${status}`;
    return request<Paginated>(url);
  },
  getReview: (id: number) => request<ReviewItem>(`/reviews/${id}`),
  approveReview: (id: number) => request<ReviewItem>(`/reviews/${id}/approve`, { method: 'POST' }),
  rejectReview: (id: number) => request<ReviewItem>(`/reviews/${id}/reject`, { method: 'POST' }),

  // Scheduler
  getPolicy: () => request<AnalysisPolicy>('/scheduler/analysis-policy'),
  updatePolicy: (patch: Partial<AnalysisPolicy>) =>
    request<AnalysisPolicy>('/scheduler/analysis-policy', { method: 'PUT', body: JSON.stringify(patch) }),

  // Messages
  listConversations: () => request<Conversations>('/messages/conversations'),
  listMessages: (page = 1, opts?: { contact_id?: string; group_id?: string }) => {
    let url = `/messages?page=${page}&page_size=50`;
    if (opts?.contact_id) url += `&contact_id=${encodeURIComponent(opts.contact_id)}`;
    if (opts?.group_id) url += `&group_id=${encodeURIComponent(opts.group_id)}`;
    return request<Paginated>(url);
  },

  // Group Members
  listGroupMembers: (groupId: string) => request<GroupMember[]>(`/groups/${encodeURIComponent(groupId)}/members`),
  updateGroupMember: (groupId: string, wxid: string, patch: Partial<GroupMember>) =>
    request<GroupMember>(`/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(wxid)}`, { method: 'PATCH', body: JSON.stringify(patch) }),

  // Proactive Chats
  listProactiveChats: () => request<ProactiveChat[]>('/proactive-chats'),
  getProactiveChat: (id: string) => request<ProactiveChat>(`/proactive-chats/${encodeURIComponent(id)}`).catch(() => null),
  upsertProactiveChat: (id: string, config: ProactiveChatConfig) =>
    request<ProactiveChat>(`/proactive-chats/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(config) }),
  deleteProactiveChat: (id: string) =>
    request<{ deleted: boolean }>(`/proactive-chats/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // Self Analysis
  selfAnalyze: () => request<{ updated: boolean; analysis?: Record<string, string>; messages_analyzed?: number; updated_fields?: string[]; chats_analyzed?: number; error?: string }>('/runtime/self-analyze', { method: 'POST' }),

  // User Profile
  getUserProfile: () => request<Record<string, string>>('/runtime/user-profile'),
  updateUserProfile: (patch: Record<string, string>) =>
    request<Record<string, string>>('/runtime/user-profile', { method: 'PUT', body: JSON.stringify(patch) }),

  // API Config
  getApiConfig: () => request<Record<string, string>>('/runtime/api-config'),
  updateApiConfig: (patch: Record<string, string>) =>
    request<Record<string, string>>('/runtime/api-config', { method: 'PUT', body: JSON.stringify(patch) }),

  // Runtime
  getRuntimeStatus: () => request<RuntimeStatus>('/runtime/status'),
  setAutoReply: (enabled: boolean) =>
    request<{ auto_reply_enabled: boolean }>('/runtime/auto-reply', { method: 'PUT', body: JSON.stringify({ enabled }) }),
  setAiLabel: (patch: { enabled?: boolean; label_text?: string }) =>
    request<{ ai_label_enabled: boolean; ai_label_text: string }>('/runtime/ai-label', { method: 'PUT', body: JSON.stringify(patch) }),
  listEvents: (page = 1) => request<Paginated>(`/runtime/events?page=${page}`),
};

// Types
export interface DashboardSummary {
  runtime_status: string;
  whitelist_count: number;
  active_group_count: number;
  pending_review_count: number;
  analysis_success_24h: number;
  analysis_failed_24h: number;
}

export interface Paginated {
  items: any[];
  page: number;
  page_size: number;
  total: number;
}

export interface Contact {
  wxid: string;
  nickname: string | null;
  remark: string | null;
  relationship: string | null;
  is_whitelist: boolean;
  is_paused: boolean;
  my_alias_for: string | null;
  persona_summary: string | null;
  style_summary: string | null;
  interaction_style_summary: string | null;
  last_analysis_at: string | null;
}

export interface Group {
  group_id: string;
  group_name: string | null;
  is_active: boolean;
  trigger_mode: string;
  keywords: string[];
  group_profile: string | null;
  reply_strategy: string | null;
  last_analysis_at: string | null;
}

export interface Rule {
  scope_type: string;
  scope_id: string;
  version: number;
  document: { metadata: Record<string, any>; chat_rules: Record<string, any> };
}

export interface AnalysisRun {
  id: number;
  target_type: string;
  target_id: string;
  trigger_type: string;
  status: string;
  summary: string | null;
  persona_json: string | null;
  suggestions_json: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface ReviewItem {
  id: number;
  review_type: string;
  target_type: string;
  target_id: string;
  status: string;
  proposed_payload_json: string;
  rationale_json: string | null;
  edited_payload_json: string | null;
  created_at: string;
}

export interface AnalysisPolicy {
  enabled: boolean;
  cron_expr: string;
  max_targets_per_run: number;
  contacts_enabled: boolean;
  groups_enabled: boolean;
  min_hours_since_last_analysis: number;
  selection_strategy: string;
  overlap_policy: string;
}

export interface RuntimeStatus {
  runtime_process: string;
  console_process: string;
  auto_reply_enabled: boolean;
  ai_label_enabled: boolean;
  ai_label_text: string;
  last_rule_reload_at: string | null;
  last_batch_analysis_at: string | null;
}

export interface ConversationItem {
  type: string;
  id: string;
  name: string;
  last_msg_at: string;
  msg_count: number;
  last_content: string;
}

export interface Conversations {
  private: ConversationItem[];
  groups: ConversationItem[];
}

export interface GroupMember {
  group_id: string;
  wxid: string;
  nickname: string | null;
  role: string;
  personality: string;
  style_notes: string;
  notes: string;
  msg_count: number;
  last_msg_at: string | null;
  // Merged contact fields
  contact_remark: string | null;
  contact_relationship: string | null;
  contact_persona: string | null;
  contact_style: string | null;
  contact_interaction: string | null;
  contact_is_whitelist: boolean | null;
  contact_my_alias: string | null;
  group_my_alias: string | null;
  // Patch fields (for update)
  relationship?: string;
  persona_summary?: string;
  contact_style_summary?: string;
  interaction_style_summary?: string;
  my_alias_for?: string;
  contact_my_alias_for?: string;
}

export interface ProactiveChat {
  id: string;
  chat_type: string;
  chat_name: string | null;
  enabled: boolean;
  interval_minutes: number;
  topic: string;
  last_sent_at: string | null;
}

export interface ProactiveChatConfig {
  chat_type: string;
  chat_name?: string;
  enabled: boolean;
  interval_minutes: number;
  topic: string;
}
