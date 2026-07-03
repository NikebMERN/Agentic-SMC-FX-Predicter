const TOKEN_KEY = "admin_token";
const USER_KEY = "admin_username";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function getUsername() {
  return localStorage.getItem(USER_KEY) || "";
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function setUsername(name) {
  if (name) localStorage.setItem(USER_KEY, name);
  else localStorage.removeItem(USER_KEY);
}

export function clearSession() {
  setToken("");
  setUsername("");
}

export async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`/admin/api${path}`, { ...options, headers });
  const body = await res.json().catch(() => ({}));

  if (res.status === 401) {
    if (path !== "/login" && !path.startsWith("/forgot") && !path.startsWith("/reset")) {
      clearSession();
      window.location.href = "/admin/login";
    }
  }

  if (!res.ok) throw new Error(body.error || res.statusText);
  return body;
}

export async function login(email, password) {
  const res = await fetch("/admin/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || "Login failed");
  setToken(body.token);
  setUsername(body.username || "");
  return body;
}

export async function forgotPassword(email) {
  const res = await fetch("/admin/api/forgot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || "Request failed");
  return body;
}

export async function resetPassword(email, code, newPassword) {
  const res = await fetch("/admin/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, new_password: newPassword }),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || "Reset failed");
  return body;
}
