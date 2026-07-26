import { useEffect, useMemo, useState } from "react";
import { getToken, login as apiLogin, logout as apiLogout, api } from "../api/client.js";
import { AuthContext } from "./auth.js";

export function AuthProvider({ children }) {
  const [token, setTokenState] = useState(getToken());
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    if (!token) {
      setProfile(null);
      return;
    }
    api("/me")
      .then(setProfile)
      .catch(() => setProfile(null));
  }, [token]);

  const value = useMemo(
    () => ({
      token,
      profile,
      isAuthenticated: Boolean(token),
      async login(email, password) {
        const res = await apiLogin(email, password);
        setTokenState(res.token);
        setProfile({
          user_id: res.user_id,
          username: res.username,
          status: res.status,
          signals_remaining: res.signals_remaining,
        });
        return res;
      },
      async logout() {
        await apiLogout();
        setTokenState("");
        setProfile(null);
      },
      setProfile,
    }),
    [token, profile]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
