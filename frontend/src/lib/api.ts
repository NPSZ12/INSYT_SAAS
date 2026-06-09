const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "https://api.insyt360.com";

function getStoredToken() {
  if (typeof window === "undefined") return null;

  return (
    localStorage.getItem("insyt_token") ||
    localStorage.getItem("insyt_access_token")
  );
}

function clearStoredSession() {
  if (typeof window === "undefined") return;

  localStorage.removeItem("insyt_token");
  localStorage.removeItem("insyt_access_token");
  localStorage.removeItem("insyt_user");
  localStorage.removeItem("insyt_selected_project");
}

function getAuthHeaders() {
  const token = getStoredToken();

  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function buildUrl(path: string) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}

export async function apiGet(path: string) {
  const url = buildUrl(path);
  console.log("API GET:", url);

  const response = await fetch(url, {
    method: "GET",
    headers: getAuthHeaders(),
    mode: "cors",
    credentials: "include",
  });

  if (!response.ok) {
    const text = await response.text();

    if (response.status === 401 && typeof window !== "undefined") {
      console.warn("API GET unauthorized:", url, text);

      clearStoredSession();
      window.location.href = "/login";
      return;
    }

    throw new Error(`API GET failed ${response.status}: ${text}`);
  }

  return response.json();
}

export async function apiPost(path: string, body: unknown) {
  const url = buildUrl(path);
  console.log("API POST:", url);

  const response = await fetch(url, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
    mode: "cors",
    credentials: "include",
  });

  if (!response.ok) {
    const text = await response.text();

    if (response.status === 401 && typeof window !== "undefined") {
      console.warn("API POST unauthorized:", url, text);

      clearStoredSession();
      window.location.href = "/login";
      return;
    }

    throw new Error(`API POST failed ${response.status}: ${text}`);
  }

  return response.json();
}