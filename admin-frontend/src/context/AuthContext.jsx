import { createContext, useContext, useMemo, useState } from "react";
import { clearSession, getToken, getUsername, login as apiLogin } from "../api/client.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(getToken());
  const [username, setUsernameState] = useState(getUsername());

  const value = useMemo(
    () => ({
      token,
      username,
      isAuthenticated: Boolean(token),
      async login(email, password) {
        const res = await apiLogin(email, password);
        setTokenState(res.token);
        setUsernameState(res.username || "");
        return res;
      },
      logout() {
        clearSession();
        setTokenState("");
        setUsernameState("");
      },
    }),
    [token, username]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
