const TOKEN_KEY = "smc_token";
const REFRESH_KEY = "smc_refresh";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY) || "";
}

export function setTokens({ token, refresh_token, access_token }) {
  const access = token || access_token;
  if (access) localStorage.setItem(TOKEN_KEY, access);
  else localStorage.removeItem(TOKEN_KEY);
  if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
  else localStorage.removeItem(REFRESH_KEY);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

async function refreshAccessToken() {
  const refresh_token = getRefreshToken();
  if (!refresh_token) return null;
  const res = await fetch("/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    clearTokens();
    return null;
  }
  setTokens(body);
  return body.token || body.access_token;
}

export async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res = await fetch(path, { ...options, headers });
  if (res.status === 401 && getRefreshToken()) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers.Authorization = `Bearer ${newToken}`;
      res = await fetch(path, { ...options, headers });
    }
  } else if (res.status === 401 && !getToken()) {
    clearTokens();
  }

  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(body.error || res.statusText);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

export async function login(email, password) {
  const res = await fetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const body = await res.json();
  if (!res.ok) {
    const err = new Error(body.error || "Login failed");
    err.status = res.status;
    err.body = body;
    throw err;
  }
  setTokens(body);
  return body;
}

export async function logout() {
  try {
    await api("/logout", { method: "POST" });
  } catch {
    /* ignore */
  }
  clearTokens();
}

export async function forgotPassword(email) {
  const res = await fetch("/forgot-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || "Request failed");
  return body;
}

export async function resetPassword(email, code, newPassword) {
  const res = await fetch("/reset-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, new_password: newPassword }),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || "Reset failed");
  return body;
}
