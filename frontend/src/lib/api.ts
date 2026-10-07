const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

/** Every API call goes through here so the session cookie is always sent. */
export function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  return fetch(url, { credentials: "include", ...init });
}

export interface IdeaItem {
  id: string;
  strategy_id: string;
  /** Target platforms of the idea's strategy, lower case. */
  platforms?: string[];
  /** Name of the strategy this idea was discovered for. */
  strategy_name?: string | null;
  title: string;
  description?: string | null;
  status: "NEW" | "SELECTED" | "IN_PROGRESS" | "PUBLISHED" | "REJECTED" | "EXPIRED";
  relevance_score?: number | null;
  trend_score?: number | null;
  novelty_score?: number | null;
  audience_fit_score?: number | null;
  source_quality_score?: number | null;
  final_score?: number | null;
  created_at: string;
  updated_at: string;
}

export interface SourceItemSummary {
  id: string;
  source_id: string;
  url: string;
  title?: string | null;
  source_type: string;
  published_at?: string | null;
  author?: string | null;
}

export interface WorkflowRunResponse {
  id: string;
  workflow_run_id?: string;
  idea_id: string;
  strategy_id: string;
  status: "PENDING" | "RUNNING" | "PAUSED" | "NEEDS_REVIEW" | "PUBLISHING" | "COMPLETED" | "FAILED" | "REJECTED" | "CANCELLED";
  current_phase?: string | null;
  started_at: string;
  resolved_at?: string | null;
  error?: string | null;
  /** False while a PENDING run waits for the scheduler worker to start it. */
  worker_running?: boolean | null;
}

export interface ResearchResponse {
  id: string;
  workflow_run_id: string;
  summary?: string | null;
  findings: Record<string, any>;
  sources: Record<string, any>;
  created_at: string;
}

export interface ContentBriefResponse {
  id: string;
  workflow_run_id: string;
  brief: Record<string, any>;
  created_at: string;
}

export interface DraftLintWarning {
  category: "leakage" | "ai_tell" | "unsupported_experience" | string;
  message: string;
}

export interface ContentVersionSummary {
  id: string;
  version_number: number;
  origin: string;
  title?: string | null;
  body: string;
  lint_warnings?: DraftLintWarning[];
  linkedin_preview?: string;
  char_count?: number;
  will_truncate?: boolean;
  created_at: string;
}

export interface ContentDraftResponse {
  content_id: string;
  workflow_run_id: string;
  current_version: ContentVersionSummary;
  versions: ContentVersionSummary[];
  lint_warnings?: DraftLintWarning[];
  linkedin_preview?: string;
  char_count?: number;
  will_truncate?: boolean;
}

export interface ApprovalDecisionResponse {
  workflow_run_id: string;
  approval_id: string;
  content_version_id: string;
  status: string;
  decision: "APPROVED" | "REJECTED" | "REVISION_REQUESTED";
  feedback?: string | null;
}

export async function fetchIdeas(status?: string, strategyId?: string, limit?: number): Promise<IdeaItem[]> {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  if (status && status !== "ALL") params.set("status", status);
  if (strategyId) params.set("strategy_id", strategyId);
  const url = params.toString() ? `${API_BASE}/ideas?${params.toString()}` : `${API_BASE}/ideas`;
  
  const res = await apiFetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch ideas: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchIdea(id: string): Promise<IdeaItem> {
  const res = await apiFetch(`${API_BASE}/ideas/${id}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch idea ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchIdeaSources(id: string): Promise<SourceItemSummary[]> {
  const res = await apiFetch(`${API_BASE}/ideas/${id}/sources`);
  if (!res.ok) {
    throw new Error(`Failed to fetch idea sources: ${res.statusText}`);
  }
  return res.json();
}

export async function startWorkflowRun(ideaId: string, strategyId: string): Promise<WorkflowRunResponse> {
  const res = await apiFetch(`${API_BASE}/workflow-runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      idea_id: ideaId,
      strategy_id: strategyId,
    }),
  });

  const data = await res.json();

  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    if (typeof data.detail === "string") {
      message = data.detail;
    } else if (data.detail && typeof data.detail === "object") {
      message = data.detail.message || JSON.stringify(data.detail);
    }
    const error = new Error(message) as Error & { status?: number; data?: any; detail?: any };
    error.status = res.status;
    error.data = data;
    error.detail = data.detail;
    throw error;
  }

  return {
    ...data,
    id: data.id || data.workflow_run_id,
    workflow_run_id: data.workflow_run_id || data.id,
    started_at: data.started_at || data.created_at,
  };
}

export async function fetchWorkflowRun(id: string): Promise<WorkflowRunResponse> {
  const res = await apiFetch(`${API_BASE}/workflow-runs/${id}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch workflow run ${id}: ${res.statusText}`);
  }
  const data = await res.json();
  return {
    ...data,
    id: data.id || data.workflow_run_id,
    started_at: data.started_at || data.created_at,
  };
}

export async function fetchWorkflowRunResearch(id: string): Promise<ResearchResponse> {
  const res = await apiFetch(`${API_BASE}/workflow-runs/${id}/research`);
  if (!res.ok) {
    throw new Error(`Failed to fetch research for workflow run ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchWorkflowRunBrief(id: string): Promise<ContentBriefResponse> {
  const res = await apiFetch(`${API_BASE}/workflow-runs/${id}/brief`);
  if (!res.ok) {
    throw new Error(`Failed to fetch brief for workflow run ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchWorkflowRunDraft(id: string): Promise<ContentDraftResponse> {
  const res = await apiFetch(`${API_BASE}/workflow-runs/${id}/draft`);
  if (!res.ok) {
    throw new Error(`Failed to fetch draft for workflow run ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function submitApprovalDecision(
  workflowRunId: string,
  contentVersionId: string,
  decision: "APPROVED" | "REJECTED" | "REVISION_REQUESTED",
  feedback?: string
): Promise<ApprovalDecisionResponse> {
  const res = await apiFetch(`${API_BASE}/workflow-runs/${workflowRunId}/approval`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      content_version_id: contentVersionId,
      decision,
      feedback: feedback || null,
    }),
  });

  const data = await res.json();
  if (!res.ok) {
    const message = data.detail || `Approval submission failed with status ${res.status}`;
    throw new Error(message);
  }
  return data;
}

export interface PublicationResponse {
  id: string;
  content_version_id: string;
  platform: string;
  status: "PENDING" | "PUBLISHING" | "PUBLISHED" | "FAILED";
  idempotency_key: string;
  external_id?: string | null;
  idea_title?: string | null;
  url?: string | null;
  publication_metadata: Record<string, any>;
  error?: string | null;
  created_at: string;
  published_at?: string | null;
  schedule_info?: {
    last_synced_at?: string | null;
    next_sync_at?: string | null;
    next_sync_overdue?: boolean;
    sync_attempt_count?: number;
    attempt_number?: number;
    network_retry_paused?: boolean;
    scheduler_running?: boolean;
  };
  analytics_status?: AnalyticsStatus | null;
}

/** One status per publication, derived by the backend from the most recent attempt. */
export interface AnalyticsStatus {
  state: "available" | "manual" | "not_collected_yet" | "network_error" | "failed" | "none" | "deleted_upstream";
  deleted_upstream_at?: string | null;
  last_attempt_at: string | null;
  last_attempt_outcome: string | null;
  last_attempt_source: "scheduler" | "manual" | null;
  last_attempt_message: string | null;
  last_attempt_technical: string | null;
  last_buffer_response_at: string | null;
  attempt_number: number;
  network_failures_in_row: number;
  network_retry_paused: boolean;
  next_sync_at: string | null;
  next_sync_overdue: boolean;
  scheduler_running: boolean;
  valid_snapshot: { id: string; collected_at: string; provider: string | null } | null;
}

export async function fetchWorkflowRunPublication(id: string): Promise<PublicationResponse> {
  const res = await apiFetch(`${API_BASE}/workflow-runs/${id}/publication`);
  if (!res.ok) {
    throw new Error(`Failed to fetch publication for workflow run ${id}: ${res.statusText}`);
  }
  return res.json();
}

export interface StrategySourceSummary {
  id: string;
  name: string;
  source_type: string;
  url?: string | null;
  enabled: boolean;
}

export interface StrategyItem {
  id: string;
  name: string;
  description?: string | null;
  archived_at?: string | null;
  config: {
    niche?: string;
    audience?: string;
    goals?: string[];
    platforms?: string[];
    content_types?: string[];
    topics?: string[];
    tone?: string;
    voice_guidelines?: string;
    discovery_interval_hours?: number;
    [key: string]: any;
  };
  enabled: boolean;
  sources: StrategySourceSummary[];
  schedule_info?: {
    interval_hours?: number | null;
    is_scheduled?: boolean;
    last_run?: {
      completed_at?: string | null;
      status?: string;
      items_found?: number;
      ideas_created?: number;
    } | null;
  };
  created_at: string;
  updated_at: string;
}

export interface CreateStrategyPayload {
  name: string;
  description?: string;
  config?: Record<string, any>;
  enabled?: boolean;
  source_ids?: string[];
}

export interface UpdateStrategyPayload {
  name?: string;
  description?: string;
  config?: Record<string, any>;
  enabled?: boolean;
  source_ids?: string[];
}

export interface StrategyDiscoveryResult {
  strategy_id: string;
  strategy_name: string;
  sources_synced: number;
  items_fetched: number;
  new_items_count: number;
  ideas_created_count: number;
  created_idea_ids: string[];
}

export interface SourceOption {
  id: string;
  name: string;
  source_type: string;
  url?: string | null;
  enabled: boolean;
  config?: Record<string, any>;
}

export async function fetchStrategies(enabledOnly = false, archived?: boolean): Promise<StrategyItem[]> {
  const params = new URLSearchParams();
  if (enabledOnly) params.set("enabled_only", "true");
  if (archived !== undefined) params.set("archived", String(archived));
  const url = `${API_BASE}/strategies${params.toString() ? `?${params.toString()}` : ""}`;
  const res = await apiFetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch strategies: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchStrategy(id: string): Promise<StrategyItem> {
  const res = await apiFetch(`${API_BASE}/strategies/${id}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch strategy ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function createStrategy(payload: CreateStrategyPayload): Promise<StrategyItem> {
  const res = await apiFetch(`${API_BASE}/strategies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Failed to create strategy");
  }
  return data;
}

export async function updateStrategy(id: string, payload: UpdateStrategyPayload): Promise<StrategyItem> {
  const res = await apiFetch(`${API_BASE}/strategies/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Failed to update strategy");
  }
  return data;
}

export async function runStrategyDiscovery(id: string): Promise<StrategyDiscoveryResult> {
  const res = await apiFetch(`${API_BASE}/strategies/${id}/discover`, {
    method: "POST",
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Failed to run strategy discovery");
  }
  return data;
}

export interface CreateSourcePayload {
  name?: string | null;
  source_type?: string;
  url?: string | null;
  enabled?: boolean;
  config?: Record<string, any>;
}

export interface UpdateSourcePayload {
  name?: string;
  source_type?: string;
  url?: string | null;
  enabled?: boolean;
  config?: Record<string, any>;
}

export async function fetchSources(): Promise<SourceOption[]> {
  const res = await apiFetch(`${API_BASE}/sources`);
  if (!res.ok) {
    throw new Error(`Failed to fetch sources: ${res.statusText}`);
  }
  return res.json();
}

export async function createSource(payload: CreateSourcePayload): Promise<SourceOption> {
  const res = await apiFetch(`${API_BASE}/sources`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Failed to create source");
  }
  return data;
}

export async function updateSource(id: string, payload: UpdateSourcePayload): Promise<SourceOption> {
  const res = await apiFetch(`${API_BASE}/sources/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Failed to update source");
  }
  return data;
}
export interface AnalyticsSnapshot {
  id: string;
  publication_id: string;
  metrics: {
    impressions?: number;
    clicks?: number;
    likes?: number;
    reactions?: number;
    comments?: number;
    shares?: number;
    engagement_rate?: number;
    is_stub?: boolean;
    is_initial?: boolean;
    provider?: string;
    post_status?: string;
    sent_at?: string;
    metrics_updated_at?: string;
    raw_metrics?: any[];
    [key: string]: any;
  };
  collected_at: string;
}

export async function fetchPublicationAnalytics(publicationId: string): Promise<AnalyticsSnapshot[]> {
  const res = await apiFetch(`${API_BASE}/publications/${publicationId}/analytics`);
  if (!res.ok) {
    throw new Error(`Failed to fetch analytics for publication ${publicationId}: ${res.statusText}`);
  }
  return res.json();
}

export async function syncPublicationAnalytics(publicationId: string): Promise<AnalyticsSnapshot> {
  const res = await apiFetch(`${API_BASE}/publications/${publicationId}/analytics/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const data = await res.json();
  if (!res.ok) {
    // Network failures arrive as { state, message, technical }; other errors as a string.
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : detail?.message || "Failed to sync publication analytics";
    const error = new Error(message) as Error & { detail?: any };
    error.detail = detail;
    throw error;
  }
  return data;
}

export interface ManualMetricsInputPayload {
  impressions: number;
  reactions: number;
  comments: number;
  clicks: number;
  shares: number;
}

export async function submitManualMetrics(
  publicationId: string,
  payload: ManualMetricsInputPayload
): Promise<AnalyticsSnapshot> {
  const res = await apiFetch(`${API_BASE}/publications/${publicationId}/analytics/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Failed to submit manual metrics");
  }
  return data;
}


export interface MediaAsset {
  id: string;
  content_version_id: string;
  type: string;
  status: string;
  storage_url: string;
  mime_type: string;
  width?: number | null;
  height?: number | null;
  alt_text?: string | null;
  prompt: string;
  provider: string;
  provider_asset_id?: string | null;
  asset_metadata: {
    is_stub?: boolean;
    size_bytes?: number;
    generator?: string;
    [key: string]: any;
  };
  created_at: string;
  updated_at: string;
}

export async function fetchVersionMedia(
  contentId: string,
  versionId: string
): Promise<MediaAsset[]> {
  const res = await apiFetch(`${API_BASE}/content/${contentId}/versions/${versionId}/media`);
  if (!res.ok) {
    throw new Error(`Failed to fetch media assets: ${res.statusText}`);
  }
  return res.json();
}

export async function generateVersionMedia(
  contentId: string,
  versionId: string,
  prompt?: string,
  regenerate: boolean = false
): Promise<MediaAsset> {
  const res = await apiFetch(`${API_BASE}/content/${contentId}/versions/${versionId}/media`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, regenerate }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Failed to generate media asset");
  }
  return data;
}

export interface AnalyticsSummaryPost {
  publication_id: string;
  workflow_run_id: string | null;
  platform: string;
  external_id: string | null;
  idea_title: string | null;
  published_at: string | null;
  has_snapshot: boolean;
  collected_at: string | null;
  provider: string | null;
  impressions: number | null;
  reactions: number | null;
  comments: number | null;
  clicks: number | null;
  shares: number | null;
  snapshot_count: number;
  is_test_post: boolean;
}

export interface AnalyticsSummary {
  post_count: number;
  posts_with_metrics: number;
  total_impressions: number;
  total_reactions: number;
  total_comments: number;
  include_test: boolean;
  posts: AnalyticsSummaryPost[];
}

export interface PlatformBreakdown {
  key: string;
  label: string;
  connected: boolean;
  post_count: number;
}

export async function fetchAnalyticsSummary(includeTest = false, platform?: string): Promise<AnalyticsSummary & { platform: string | null; platforms: PlatformBreakdown[] }> {
  const qs = new URLSearchParams({ include_test: String(includeTest) });
  if (platform) qs.set("platform", platform);
  const res = await apiFetch(`${API_BASE}/analytics/summary?${qs.toString()}`);
  if (!res.ok) throw new Error(`Failed to load analytics summary: ${res.statusText}`);
  return res.json();
}

/** Error text from a failed response: the backend's detail string, or detail.message. */
async function errorFrom(res: Response, fallback: string): Promise<Error> {
  try {
    const body = await res.json();
    const d = body?.detail;
    const message = typeof d === "string" ? d : d?.message ?? d?.detail ?? fallback;
    return new Error(String(message));
  } catch {
    return new Error(fallback);
  }
}

export async function saveDraftEdit(runId: string, edit: { title: string | null; body: string }) {
  const res = await apiFetch(`${API_BASE}/workflow-runs/${runId}/draft/versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(edit),
  });
  if (!res.ok) throw await errorFrom(res, "Could not save the edit.");
  return res.json();
}

export async function archiveIdea(id: string) {
  const res = await apiFetch(`${API_BASE}/ideas/${id}/archive`, { method: "POST" });
  if (!res.ok) throw await errorFrom(res, "Could not archive the idea.");
  return res.json();
}

export async function restoreIdea(id: string) {
  const res = await apiFetch(`${API_BASE}/ideas/${id}/restore`, { method: "POST" });
  if (!res.ok) throw await errorFrom(res, "Could not restore the idea.");
  return res.json();
}

export async function deleteIdea(id: string, stopRunning = true): Promise<{ status: "deleted" | "stopping"; message?: string }> {
  // stopRunning: first stop the idea's workflow runs, then delete them with it.
  const res = await apiFetch(`${API_BASE}/ideas/${id}?stop_running=${stopRunning}`, { method: "DELETE" });
  if (!res.ok) throw await errorFrom(res, "Could not delete the idea.");
  return res.json();
}

export async function archiveStrategy(id: string) {
  const res = await apiFetch(`${API_BASE}/strategies/${id}/archive`, { method: "POST" });
  if (!res.ok) throw await errorFrom(res, "Could not archive the strategy.");
}

export async function restoreStrategy(id: string) {
  const res = await apiFetch(`${API_BASE}/strategies/${id}/restore`, { method: "POST" });
  if (!res.ok) throw await errorFrom(res, "Could not restore the strategy.");
}

export async function deleteStrategy(id: string) {
  const res = await apiFetch(`${API_BASE}/strategies/${id}`, { method: "DELETE" });
  if (!res.ok) throw await errorFrom(res, "Could not delete the strategy.");
  return res.json();
}

export interface PlatformSetting {
  key: string;
  label: string;
  display_name: string;
  enabled: boolean;
  channel_id: string | null;
  notes: string | null;
  publishes_via: string | null;
  state: "ready" | "needs_token" | "disabled" | "needs_channel" | "no_provider";
  ready: boolean;
  reason: string;
  updated_at: string | null;
}

export async function fetchPlatformSettings(): Promise<PlatformSetting[]> {
  const res = await settingsCall(`/settings/platforms`);
  if (!res.ok) throw await errorFrom(res, "Could not load platform settings.");
  return res.json();
}

export async function savePlatformSettings(
  key: string,
  body: { enabled: boolean; display_name: string | null; channel_id: string | null; notes: string | null }
): Promise<PlatformSetting> {
  const res = await settingsCall(`/settings/platforms/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await errorFrom(res, "Could not save.");
  return res.json();
}

export async function testPlatformConnection(key: string): Promise<{ ok: boolean; message: string }> {
  const res = await settingsCall(`/settings/platforms/${key}/test`, { method: "POST" });
  if (!res.ok) throw await errorFrom(res, "Test failed.");
  return res.json();
}

// ---------- Settings access (password and session) ----------

export interface SettingsAuthState {
  configured: boolean;
  unlocked: boolean;
  locked_until: string | null;
}

async function settingsCall(path: string, init?: RequestInit): Promise<Response> {
  // credentials: include sends the Settings session cookie, which the browser drops when it closes.
  return apiFetch(`${API_BASE}${path}`, { credentials: "include", ...init });
}

export async function fetchSettingsAuth(): Promise<SettingsAuthState> {
  const res = await settingsCall("/settings/auth/status");
  if (!res.ok) throw await errorFrom(res, "Could not check Settings access.");
  return res.json();
}

export async function setupSettingsPassword(password: string): Promise<void> {
  const res = await settingsCall("/settings/auth/setup", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }),
  });
  if (!res.ok) throw await errorFrom(res, "Could not set the password.");
}

export async function loginSettings(password: string): Promise<void> {
  const res = await settingsCall("/settings/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }),
  });
  if (!res.ok) throw await errorFrom(res, "Could not sign in.");
}

export async function logoutSettings(): Promise<void> {
  await settingsCall("/settings/auth/logout", { method: "POST" });
}

export interface ApiKeyState {
  name: string;
  label: string;
  saved_in_app: boolean;
  last4: string | null;
  from_env: boolean;
  is_set: boolean;
  updated_at: string | null;
}

export async function fetchApiKeys(): Promise<ApiKeyState[]> {
  const res = await settingsCall("/settings/keys");
  if (!res.ok) throw await errorFrom(res, "Could not load API keys.");
  return res.json();
}

export async function saveApiKey(name: string, value: string): Promise<void> {
  const res = await settingsCall(`/settings/keys/${name}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ value }),
  });
  if (!res.ok) throw await errorFrom(res, "Could not save the key.");
}

export async function removeApiKey(name: string): Promise<void> {
  const res = await settingsCall(`/settings/keys/${name}`, { method: "DELETE" });
  if (!res.ok) throw await errorFrom(res, "Could not remove the key.");
}

// ---------- Accounts (login for the whole app) ----------

export interface Account {
  id: string;
  email: string;
  display_name: string | null;
  auth_provider: string;
  is_admin: boolean;
  has_password: boolean;
}

export interface AuthProviders {
  local: { enabled: boolean };
  google: { enabled: boolean };
  supabase: { enabled: boolean; reason?: string };
}

/** The signed-in account, or null when nobody is logged in. */
export async function fetchMe(): Promise<Account | null> {
  const res = await apiFetch(`${API_BASE}/auth/me`);
  if (res.status === 401) return null;
  if (!res.ok) throw await errorFrom(res, "Could not check your login.");
  return res.json();
}

export async function fetchAuthProviders(): Promise<AuthProviders> {
  const res = await apiFetch(`${API_BASE}/auth/providers`);
  if (!res.ok) throw await errorFrom(res, "Could not load sign-in options.");
  return res.json();
}

export async function loginAccount(email: string, password: string): Promise<Account> {
  const res = await apiFetch(`${API_BASE}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw await errorFrom(res, "Could not log in.");
  return res.json();
}

export async function registerAccount(email: string, password: string, displayName: string): Promise<Account> {
  const res = await apiFetch(`${API_BASE}/auth/register`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName || null }),
  });
  if (!res.ok) throw await errorFrom(res, "Could not create the account.");
  return res.json();
}

export async function logoutAccount(): Promise<void> {
  await apiFetch(`${API_BASE}/auth/logout`, { method: "POST" });
}

export const GOOGLE_LOGIN_URL = `${API_BASE}/auth/google/start`;

export async function retryPublish(workflowRunId: string): Promise<WorkflowRunResponse> {
  const res = await apiFetch(`${API_BASE}/workflow-runs/${workflowRunId}/retry-publish`, { method: "POST" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Retry failed (HTTP ${res.status})`);
  }
  return res.json();
}

export interface SourceSuggestion {
  name: string;
  url: string;
  topic: string;
}

export async function fetchSourceSuggestions(): Promise<SourceSuggestion[]> {
  const res = await apiFetch(`${API_BASE}/sources/suggestions`);
  if (!res.ok) {
    throw new Error(`Failed to fetch suggestions: ${res.statusText}`);
  }
  return res.json();
}

export async function selectIdea(id: string) {
  const res = await apiFetch(`${API_BASE}/ideas/${id}/select`, { method: "POST" });
  if (!res.ok) throw await errorFrom(res, "Could not select the idea.");
  return res.json();
}

export async function changePassword(current_password: string | null, new_password: string) {
  const res = await apiFetch(`${API_BASE}/auth/password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password, new_password }),
  });
  if (!res.ok) throw await errorFrom(res, "Could not change the password.");
  return res.json();
}

export async function requestPasswordReset(email: string) {
  const res = await apiFetch(`${API_BASE}/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw await errorFrom(res, "Could not request a reset code.");
  return res.json();
}

export async function resetPassword(email: string, code: string, new_password: string) {
  const res = await apiFetch(`${API_BASE}/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, new_password }),
  });
  if (!res.ok) throw await errorFrom(res, "Could not reset the password.");
  return res.json();
}
