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
  idea_id: string;
  strategy_id: string;
  status: "PENDING" | "RUNNING" | "PAUSED" | "NEEDS_REVIEW" | "PUBLISHING" | "COMPLETED" | "FAILED" | "REJECTED" | "CANCELLED";
  current_phase?: string | null;
  started_at: string;
  resolved_at?: string | null;
  error?: string | null;
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

  return data;
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
