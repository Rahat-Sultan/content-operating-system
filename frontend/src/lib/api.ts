const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export interface IdeaItem {
  id: string;
  strategy_id: string;
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

export interface ContentVersionSummary {
  id: string;
  version_number: number;
  origin: string;
  title?: string | null;
  body: string;
  created_at: string;
}

export interface ContentDraftResponse {
  content_id: string;
  workflow_run_id: string;
  current_version: ContentVersionSummary;
  versions: ContentVersionSummary[];
}

export interface ApprovalDecisionResponse {
  workflow_run_id: string;
  approval_id: string;
  content_version_id: string;
  status: string;
  decision: "APPROVED" | "REJECTED" | "REVISION_REQUESTED";
  feedback?: string | null;
}

export async function fetchIdeas(status?: string): Promise<IdeaItem[]> {
  const url = status && status !== "ALL" 
    ? `${API_BASE}/ideas?status=${encodeURIComponent(status)}`
    : `${API_BASE}/ideas`;
  
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch ideas: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchIdea(id: string): Promise<IdeaItem> {
  const res = await fetch(`${API_BASE}/ideas/${id}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch idea ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchIdeaSources(id: string): Promise<SourceItemSummary[]> {
  const res = await fetch(`${API_BASE}/ideas/${id}/sources`);
  if (!res.ok) {
    throw new Error(`Failed to fetch idea sources: ${res.statusText}`);
  }
  return res.json();
}

export async function startWorkflowRun(ideaId: string, strategyId: string): Promise<WorkflowRunResponse> {
  const res = await fetch(`${API_BASE}/workflow-runs`, {
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
    // Pass detail from backend error response (e.g. 409 detail)
    const message = data.detail || `Request failed with status ${res.status}`;
    const error = new Error(message) as Error & { status?: number; data?: any };
    error.status = res.status;
    error.data = data;
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
  const res = await fetch(`${API_BASE}/workflow-runs/${id}`);
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
  const res = await fetch(`${API_BASE}/workflow-runs/${id}/research`);
  if (!res.ok) {
    throw new Error(`Failed to fetch research for workflow run ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchWorkflowRunBrief(id: string): Promise<ContentBriefResponse> {
  const res = await fetch(`${API_BASE}/workflow-runs/${id}/brief`);
  if (!res.ok) {
    throw new Error(`Failed to fetch brief for workflow run ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchWorkflowRunDraft(id: string): Promise<ContentDraftResponse> {
  const res = await fetch(`${API_BASE}/workflow-runs/${id}/draft`);
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
  const res = await fetch(`${API_BASE}/workflow-runs/${workflowRunId}/approval`, {
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
