/** Typed API client for the GBP Overlay backend. */

// ---------- Types ----------

export interface Project {
  id: number;
  session_id: string;
  client_name: string | null;
  website_url: string | null;
  keywords: string; // JSON array string
  locations: string | null; // JSON array string
  font: string;
  images_per_page: number;
  fetch_anywhere: boolean;
  js_rendered: boolean;
  status: string;
  celery_task_id: string | null;
  created_at: string;
}

export interface ProjectImage {
  id: number;
  project_id: number;
  source_url: string | null;
  source_page_url: string | null;
  location: string | null;
  keyword: string | null;
  image_hash: string | null;
  classification: string | null;
  confidence: number | null;
  overlay_position: string | null;
  original_path: string | null;
  processed_path: string | null;
  status: string;
  width: number | null;
  height: number | null;
}

export interface KeywordGroup {
  keyword: string;
  images: ProjectImage[];
}

export interface ProjectDetail {
  project: Project;
  keyword_groups: KeywordGroup[];
  auto_skipped: ProjectImage[];
  duplicates: ProjectImage[];
  skipped: ProjectImage[];
  keywords: string[];
  all_locations: string[];
  active_count: number;
}

export interface PipelineStatus {
  status: string;
  overall_progress?: number;
  message?: string;
  stage_number?: number;
  stage?: string;
  result?: unknown;
  error?: string;
}

export interface GenerationStatus {
  status: string;
  current?: number;
  total?: number;
  message?: string;
  latest_preview?: string;
  project_id?: number;
  result?: unknown;
  error?: string;
}

export interface ProjectSummary {
  id: number;
  client_name: string | null;
  website_url: string | null;
  status: string;
  created_at: string;
  resume_url: string;
  image_count?: number | null;
  zip_size?: number | null;
  has_download?: boolean;
}

export interface ProjectsResponse {
  active: ProjectSummary[];
  completed: ProjectSummary[];
  failed: ProjectSummary[];
}

export interface ConfirmPayload {
  included_images: number[];
  overrides: Array<{ image_id: number; keyword?: string; location?: string }>;
}

// ---------- API Error ----------

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------- Fetch Wrapper ----------

// Default request timeout (30s) to prevent indefinite hangs
const DEFAULT_TIMEOUT_MS = 30_000;

async function apiFetch<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  // Allow callers to pass their own signal (e.g., for debounce cancellation)
  // by merging with our timeout signal
  const callerSignal = options.signal;
  if (callerSignal) {
    callerSignal.addEventListener("abort", () => controller.abort());
  }

  try {
    const res = await fetch(url, {
      ...options,
      credentials: "same-origin",
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "Unknown error");
      throw new ApiError(res.status, text);
    }

    return res.json() as Promise<T>;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "Request timed out or was cancelled");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---------- Endpoints ----------

export async function createProject(formData: FormData): Promise<{ id: number; status: string }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 60_000);

  try {
    const res = await fetch("/api/projects", {
      method: "POST",
      body: formData,
      credentials: "same-origin",
      signal: controller.signal,
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({ error: "Unknown error" }));
      throw new ApiError(res.status, (body as { error?: string }).error ?? "Failed to create project");
    }

    return res.json() as Promise<{ id: number; status: string }>;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "Request timed out");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

export function fetchProject(id: number): Promise<ProjectDetail> {
  return apiFetch(`/api/projects/${id}`);
}

export function fetchPipelineStatus(id: number): Promise<PipelineStatus> {
  return apiFetch(`/api/projects/${id}/status`);
}

export function fetchGenerationStatus(id: number): Promise<GenerationStatus> {
  return apiFetch(`/api/projects/${id}/generation-status`);
}

export function fetchProjects(): Promise<ProjectsResponse> {
  return apiFetch("/api/projects");
}

export async function confirmReview(
  projectId: number,
  payload: ConfirmPayload,
): Promise<{ id: number; status: string }> {
  return apiFetch(`/api/projects/${projectId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateImageKeyword(
  imageId: number,
  keyword: string,
  options?: { signal?: AbortSignal },
): Promise<{ id: number; keyword: string }> {
  return apiFetch(`/api/images/${imageId}/keyword`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keyword }),
    signal: options?.signal,
  });
}

export async function updateImageLocation(
  imageId: number,
  location: string,
  options?: { signal?: AbortSignal },
): Promise<{ id: number; location: string }> {
  return apiFetch(`/api/images/${imageId}/location`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ location }),
    signal: options?.signal,
  });
}

export async function updateImageStatus(imageId: number, status: string): Promise<{ id: number; status: string }> {
  return apiFetch(`/api/images/${imageId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export async function restoreImage(imageId: number): Promise<{ id: number; status: string }> {
  return apiFetch(`/api/images/${imageId}/restore`, {
    method: "PATCH",
  });
}

export function getPreviewImageUrl(projectId: number, imageId: number): string {
  return `/api/projects/${projectId}/images/${imageId}/preview`;
}

export function getDownloadUrl(projectId: number): string {
  return `/api/projects/${projectId}/download`;
}

export async function downloadZip(projectId: number): Promise<void> {
  const res = await fetch(getDownloadUrl(projectId), {
    credentials: "same-origin",
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: "Download failed" }));
    throw new ApiError(res.status, (body as { error?: string }).error ?? "Download failed");
  }

  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition");
  const filenameMatch = disposition?.match(/filename="?([^"]+)"?/);
  const filename = filenameMatch?.[1] ?? `project-${projectId}.zip`;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function getFonts(): Record<string, { bold: string; regular: string }> {
  return {
    Montserrat: { bold: "Montserrat-Bold.ttf", regular: "Montserrat-SemiBold.ttf" },
    Poppins: { bold: "Poppins-Bold.ttf", regular: "Poppins-SemiBold.ttf" },
    Oswald: { bold: "Oswald-Bold.ttf", regular: "Oswald-SemiBold.ttf" },
    Roboto: { bold: "Roboto-Bold.ttf", regular: "Roboto-Medium.ttf" },
    "Playfair Display": { bold: "Playfair-Display-Bold.ttf", regular: "Playfair-Display-SemiBold.ttf" },
    Lato: { bold: "Lato-Bold.ttf", regular: "Lato-Regular.ttf" },
    "Bebas Neue": { bold: "BebasNeue-Regular.ttf", regular: "BebasNeue-Regular.ttf" },
    Raleway: { bold: "Raleway-Bold.ttf", regular: "Raleway-SemiBold.ttf" },
    Nunito: { bold: "Nunito-Bold.ttf", regular: "Nunito-SemiBold.ttf" },
  };
}
