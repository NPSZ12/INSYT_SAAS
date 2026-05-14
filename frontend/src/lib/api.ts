const API_BASE_URL = "http://localhost:8000";

function getStoredUsername() {
  if (typeof window === "undefined") {
    return "";
  }

  const storedUser = localStorage.getItem("insyt_user");

  if (!storedUser) {
    return "";
  }

  try {
    const user = JSON.parse(storedUser);
    return user.username || "";
  } catch {
    return "";
  }
}

export async function apiGet(path: string) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "X-Username": getStoredUsername(),
    },
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json();
}

export async function apiPost(path: string, data: unknown) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Username": getStoredUsername(),
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json();
}