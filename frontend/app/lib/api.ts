const API = "/api";
const TOKEN_KEY = "research_api_token";

export function authToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function storeAuthToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const token = authToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function redirectIfUnauthorized(path: string, status: number) {
  if (status !== 401 || path.startsWith("/auth/") || typeof window === "undefined") return;
  if (window.location.pathname.startsWith("/login")) return;
  const next = `${window.location.pathname}${window.location.search}`;
  window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

async function parseError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const json = JSON.parse(text) as { detail?: string | { msg?: string }[] };
    if (typeof json.detail === "string") return json.detail;
    if (Array.isArray(json.detail)) {
      return json.detail.map((d) => d.msg ?? String(d)).join("; ");
    }
  } catch {
    /* plain text */
  }
  return text || res.statusText;
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...authHeaders(), ...init?.headers },
  });
  if (!res.ok) {
    redirectIfUnauthorized(path, res.status);
    throw new ApiError(res.status, await parseError(res));
  }
  return res.json() as Promise<T>;
}

export async function apiSend<T>(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method,
    ...init,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...authHeaders(),
      ...init?.headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    redirectIfUnauthorized(path, res.status);
    throw new ApiError(res.status, await parseError(res));
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export type AuthState = {
  authenticated: boolean;
  configured: boolean;
  username: string | null;
};

export type LoginResult = {
  token: string;
  token_type: "Bearer";
  expires_at: number;
  username: string;
};

export function fetchAuth() {
  return apiGet<AuthState>("/auth/me");
}

export async function login(username: string, password: string) {
  const result = await apiSend<LoginResult>("/auth/login", "POST", { username, password });
  storeAuthToken(result.token);
  return result;
}

export function logout() {
  clearAuthToken();
}

export type ResearchPreset = {
  id: string;
  label: string;
  binary: string;
  hint: string;
  command: string;
  available: boolean;
};

export type StatusResponse = {
  github_token: boolean;
  github_token_source?: string;
  research_dir: string;
  command_code_model?: string;
  db_path: string;
  research_command: string;
  research_preset: string;
  research_presets: ResearchPreset[];
  default_research_command: string;
  sast: SastSettings;
};

export type SastSettings = {
  sast_enabled?: boolean;
  sast_tool?: string;
  sast_timeout?: number;
};

export type Organization = {
  id?: number;
  login: string;
  name?: string;
  html_url?: string;
  project_count?: number;
  researched_count?: number;
  skipped_count?: number;
  scanned_at?: string;
};

export type Project = {
  id: number;
  full_name: string;
  html_url?: string;
  description?: string;
  language?: string;
  stars?: number;
  research_score?: number;
  research_status?: string;
  last_report?: string;
  notes?: string;
  org_id?: number;
  skipped?: number | boolean;
  reported?: number | boolean;
  false_positive?: number | boolean;
  project_types?: string | string[];
  local_path?: string | null;
  last_job_id?: number;
  on_disk?: boolean;
  in_history?: boolean;
  researched_at?: string | null;
  researched?: boolean;
};

export type SearchCursor = {
  org_login?: string;
  filter_key?: string;
  github_page?: number;
  exhausted?: boolean;
  total_discovered?: number;
  star_ceiling?: number | null;
  time_ceiling?: string | null;
};

export type ScanResponse = {
  organization: Organization;
  projects: Project[];
  organizations?: Organization[];
  message?: string;
  added_count?: number;
  result_count?: number;
  cursor?: SearchCursor | null;
  catchup_count?: number;
  skipped_docs?: number;
  mode?: string;
};

export type Job = {
  id: number;
  project_id: number;
  status: string;
  command?: string;
  kind?: string;
  run_id?: number | null;
  created_at?: string;
  finished_at?: string;
  error?: string;
  error_step?: string | null;
  cli_session_id?: string | null;
  cli_activity?: string | null;
  log?: string;
  report?: string | null;
};

export type ScanRequest = {
  org_url: string;
  min_stars?: number;
  max_age_days?: number;
  created_within_days?: number;
  sort_by?: string;
  project_types?: string[];
  max_results?: number;
  mode?: "fresh" | "continue";
};

export type LatestResponse = {
  organization: Organization | null;
  projects: Project[];
  organizations: Organization[];
  scans: ScanRecord[];
};

export type ScanRecord = {
  id: number;
  org_login?: string;
  org_url?: string;
  status?: string;
  result_count?: number;
  mode?: string;
  added_count?: number;
  created_at?: string;
  finished_at?: string;
};

export type Conversation = {
  id: number;
  title: string;
  created_at?: string;
  updated_at?: string;
};

export type ChatMessage = {
  id: number;
  conversation_id: number;
  role: string;
  type: string;
  content: string;
  created_at?: string;
};

export type Skill = {
  id: number;
  slug: string;
  name: string;
  language?: string | null;
  description?: string;
  content: string;
  source?: string;
  created_at?: string;
  updated_at?: string;
};

export type Prompt = {
  id: number;
  slug: string;
  name: string;
  language?: string | null;
  vuln_class?: string | null;
  description?: string;
  content: string;
  created_at?: string;
  updated_at?: string;
};

export type Run = {
  id: number;
  status: string;
  conversation_id?: number | null;
  plan?: Record<string, unknown> | string;
  created_at?: string;
  finished_at?: string;
  tasks?: RunTask[];
};

export type RunTask = {
  id: number;
  run_id: number;
  project_id: number;
  job_id?: number | null;
  status: string;
  skill_slug?: string | null;
  prompt_slug?: string | null;
  full_name?: string;
  created_at?: string;
  finished_at?: string;
  job_error?: string | null;
  job_error_step?: string | null;
  job_status?: string | null;
  has_report?: number | boolean;
};

export type Finding = {
  id: number;
  project_id: number;
  title?: string;
  severity?: string;
  cwe?: string;
  file_path?: string;
  line_start?: number | null;
  description?: string;
  status?: string;
  evidence?: string;
  updated_at?: string;
  full_name?: string;
};

export type SettingsResponse = {
  research_command: string;
  research_preset: string;
  default_research_command: string;
  presets: ResearchPreset[];
  is_custom?: boolean;
};

export type JobStreamEvent = {
  type: string;
  line?: string;
  job?: Job;
  project?: Project;
  detail?: string;
  [key: string]: unknown;
};

export type ChatStreamEvent = {
  type: "token" | "thinking" | "tool_call" | "tool_result" | "done" | "error" | string;
  content?: string;
  name?: string;
  arguments?: string;
  result?: string;
  message?: string;
};

export function fetchStatus() {
  return apiGet<StatusResponse>("/status");
}

export function fetchLatest() {
  return apiGet<LatestResponse>("/latest");
}

export function fetchSettings() {
  return apiGet<SettingsResponse>("/settings");
}

export function updateSettings(body: {
  research_command: string;
  research_preset?: string | null;
}) {
  return apiSend<SettingsResponse>("/settings", "PUT", body);
}

export function fetchAiSettings() {
  return apiGet<Record<string, unknown>>("/settings/ai");
}

export function updateAiSettings(body: Record<string, unknown>) {
  return apiSend<Record<string, unknown>>("/settings/ai", "PUT", body);
}

export function testAiSettings() {
  return apiSend<Record<string, unknown>>("/settings/ai/test", "POST");
}

export function fetchGithubSettings() {
  return apiGet<Record<string, unknown>>("/settings/github");
}

export function updateGithubSettings(body: Record<string, unknown>) {
  return apiSend<Record<string, unknown>>("/settings/github", "PUT", body);
}

export function testGithubSettings() {
  return apiSend<Record<string, unknown>>("/settings/github/test", "POST");
}

export function fetchSastSettings() {
  return apiGet<SastSettings>("/settings/sast");
}

export function updateSastSettings(body: SastSettings) {
  return apiSend<SastSettings>("/settings/sast", "PUT", body);
}

export function fetchProjects(params?: Record<string, string | number | undefined>) {
  const q = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") q.set(k, String(v));
    }
  }
  const qs = q.toString();
  return apiGet<{
    organization: Organization | null;
    projects: Project[];
    organizations: Organization[];
    cursor?: SearchCursor | null;
  }>(`/projects${qs ? `?${qs}` : ""}`);
}

export function fetchOrgs() {
  return apiGet<{ organizations: Organization[] }>("/orgs");
}

export function fetchLibrary(view: "all" | "active" | "history" = "active") {
  return apiGet<{
    projects: Project[];
    view: string;
    counts?: { all?: number; active?: number; history?: number };
  }>(`/library?view=${view}`);
}

export function fetchProject(id: number) {
  return apiGet<{ project: Project; jobs: Job[] }>(`/projects/${id}`);
}

export function patchProject(
  id: number,
  body: { skipped?: boolean; reported?: boolean; false_positive?: boolean },
) {
  return apiSend<{
    project: Project;
    organizations?: Organization[];
    organization_login?: string | null;
  }>(`/projects/${id}`, "PATCH", body);
}

export function deleteProject(id: number, mode: "clone" | "full" = "full") {
  return apiSend<{
    ok: boolean;
    mode: string;
    project: Project;
    message?: string;
    organizations?: Organization[];
  }>(`/projects/${id}?mode=${mode}`, "DELETE");
}

export function startResearch(projectId: number, command?: string) {
  return apiSend<{ job: Job; project: Project; created: boolean }>(
    `/projects/${projectId}/research`,
    "POST",
    command !== undefined ? { command } : {},
  );
}

export function scanOrg(body: ScanRequest) {
  return apiSend<ScanResponse>("/scan", "POST", body);
}

export function researchRepo(repo_url: string, command?: string) {
  return apiSend<{ project: Project; job: Job; created?: boolean }>(
    "/research/repo",
    "POST",
    command !== undefined ? { repo_url, command } : { repo_url },
  );
}

export type JobFollowup = {
  id: number;
  parent_job_id?: number;
  message: string;
  status: string;
  job_id?: number | null;
  created_at?: string;
};

export type LiveJob = {
  id: number;
  project_id: number;
  run_id?: number | null;
  status: string;
  full_name: string;
  cli_activity?: string | null;
  cli_session_id?: string | null;
  error_step?: string | null;
  created_at?: string;
};

export function fetchLiveJobs() {
  return apiGet<{ jobs: LiveJob[] }>("/jobs/live");
}

export function fetchJob(jobId: number) {
  return apiGet<{ job: Job; project: Project; followups?: JobFollowup[] }>(`/jobs/${jobId}`);
}

export function followUpJob(jobId: number, message: string) {
  return apiSend<{
    followup_id: number;
    waiting: boolean;
    job_id: number | null;
    project_id: number;
    detail?: string;
  }>(`/jobs/${jobId}/follow-up`, "POST", { message });
}

export function fetchConversations() {
  return apiGet<{ conversations: Conversation[] }>("/chat/conversations");
}

export function createConversation(title?: string) {
  return apiSend<{ conversation: Conversation }>(
    "/chat/conversations",
    "POST",
    title ? { title } : {},
  );
}

export function deleteConversation(id: number) {
  return apiSend<{ ok: boolean; id: number }>(`/chat/conversations/${id}`, "DELETE");
}

export function fetchMessages(conversationId: number) {
  return apiGet<{ messages: ChatMessage[] }>(
    `/chat/conversations/${conversationId}/messages`,
  );
}

export type Experience = {
  id: number;
  domain: string;
  cue: string;
  lesson: string;
  evidence: string;
  confidence?: string;
  status?: string;
  job_id?: number | null;
  created_at?: string;
};

export type HarnessComponent = {
  id: number;
  name: string;
  version: number;
  content: string;
  status: string;
  note?: string | null;
  created_at?: string;
};

export function fetchAgentMemory() {
  return apiGet<{ snapshot: Record<string, unknown>; text: string }>("/agent/memory");
}

export function fetchExperiences(domain?: string) {
  const qs = domain ? `?domain=${encodeURIComponent(domain)}` : "";
  return apiGet<{ experiences: Experience[] }>(`/agent/experiences${qs}`);
}

export function fetchHarness() {
  return apiGet<{ components: HarnessComponent[] }>("/agent/harness");
}

export function adoptHarness(componentId: number) {
  return apiSend<{ component: HarnessComponent }>(
    `/agent/harness/${componentId}/adopt`,
    "POST",
  );
}

export function rollbackHarness(name: string) {
  return apiSend<{ component: HarnessComponent }>(
    `/agent/harness/${encodeURIComponent(name)}/rollback`,
    "POST",
  );
}

export function fetchSkills(q?: string) {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  return apiGet<{ skills: Skill[] }>(`/skills${qs}`);
}

export function createSkill(body: Omit<Skill, "id" | "source" | "created_at" | "updated_at">) {
  return apiSend<{ skill: Skill }>("/skills", "POST", body);
}

export function updateSkill(id: number, body: Partial<Skill>) {
  return apiSend<{ skill: Skill }>(`/skills/${id}`, "PUT", body);
}

export function deleteSkill(id: number) {
  return apiSend<{ ok: boolean }>(`/skills/${id}`, "DELETE");
}

export function fetchPrompts(q?: string) {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  return apiGet<{ prompts: Prompt[] }>(`/prompts${qs}`);
}

export function createPrompt(
  body: Omit<Prompt, "id" | "created_at" | "updated_at">,
) {
  return apiSend<{ prompt: Prompt }>("/prompts", "POST", body);
}

export function updatePrompt(id: number, body: Partial<Prompt>) {
  return apiSend<{ prompt: Prompt }>(`/prompts/${id}`, "PUT", body);
}

export function deletePrompt(id: number) {
  return apiSend<{ ok: boolean }>(`/prompts/${id}`, "DELETE");
}

export function fetchRuns(limit = 50) {
  return apiGet<{ runs: Run[] }>(`/runs?limit=${limit}`);
}

export function fetchRun(id: number) {
  return apiGet<{ run: Run }>(`/runs/${id}`);
}

export function fetchFindings(projectId?: number, limit = 200) {
  const q = new URLSearchParams({ limit: String(limit) });
  if (projectId !== undefined) q.set("project_id", String(projectId));
  return apiGet<{ findings: Finding[] }>(`/findings?${q}`);
}

export function patchFinding(id: number, body: Partial<Finding>) {
  return apiSend<{ finding: Finding }>(`/findings/${id}`, "PATCH", body);
}

export function parseProjectFindings(projectId: number) {
  return apiSend<Record<string, unknown>>(
    `/projects/${projectId}/findings/parse`,
    "POST",
  );
}

async function consumeSse<T>(
  res: Response,
  onEvent: (event: T) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    if (signal?.aborted) {
      await reader.cancel();
      break;
    }
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;
        try {
          onEvent(JSON.parse(raw) as T);
        } catch {
          /* skip malformed */
        }
      }
    }
  }
}

export function streamJobLogs(
  jobId: number,
  onChunk: (data: JobStreamEvent) => void,
  signal?: AbortSignal,
): () => void {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);
  void (async () => {
    try {
      const res = await fetch(`${API}/jobs/${jobId}/stream`, {
        headers: { Accept: "text/event-stream", ...authHeaders() },
        signal: controller.signal,
      });
      if (!res.ok) {
        redirectIfUnauthorized(`/jobs/${jobId}/stream`, res.status);
        return;
      }
      await consumeSse(res, onChunk, controller.signal);
    } catch {
      /* stream closed */
    }
  })();
  return () => {
    signal?.removeEventListener("abort", onAbort);
    controller.abort();
  };
}

export async function streamChatMessage(
  conversationId: number,
  content: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API}/chat/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...authHeaders(),
    },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!res.ok) {
    redirectIfUnauthorized(`/chat/conversations/${conversationId}/messages`, res.status);
    throw new ApiError(res.status, await parseError(res));
  }
  await consumeSse<ChatStreamEvent>(res, onEvent, signal);
}
