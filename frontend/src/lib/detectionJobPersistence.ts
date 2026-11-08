export type DetectionWorkspace = "capture" | "discovery";

export function detectionJobStorageKey(
  workspace: DetectionWorkspace,
  client: string,
  project: string
): string | null {
  if (!client.trim() || !project.trim()) return null;

  return [
    "insyt",
    "detection-job",
    "v1",
    encodeURIComponent(workspace),
    encodeURIComponent(client),
    encodeURIComponent(project),
  ].join(":");
}

export function readDetectionJobId(key: string | null): string {
  if (!key || typeof window === "undefined") return "";

  try {
    const value = window.localStorage.getItem(key) || "";
    return /^DET-[A-Z0-9]{16}$/.test(value) ? value : "";
  } catch {
    return "";
  }
}

export function saveDetectionJobId(
  key: string | null,
  jobId: string
): void {
  if (!key || typeof window === "undefined") return;
  if (!/^DET-[A-Z0-9]{16}$/.test(jobId)) return;

  try {
    window.localStorage.setItem(key, jobId);
  } catch {
    // Status polling still works in the current page session.
  }
}
