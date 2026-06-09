export function clearInsytSession() {
  if (typeof window === "undefined") return;

  localStorage.removeItem("insyt_token");
  localStorage.removeItem("insyt_access_token");
  localStorage.removeItem("insyt_user");
  localStorage.removeItem("insyt_selected_project");
  localStorage.removeItem("insyt_selected_client");
  localStorage.removeItem("insyt_workspace");
}

export function storeInsytSession(token: string, user: unknown) {
  if (typeof window === "undefined") return;

  clearInsytSession();

  localStorage.setItem("insyt_token", token);
  localStorage.setItem("insyt_access_token", token);
  localStorage.setItem("insyt_user", JSON.stringify(user));
}