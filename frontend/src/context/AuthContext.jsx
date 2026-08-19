import { createContext, useContext, useEffect, useState } from "react";
import client from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem("expms_user");
    return raw ? JSON.parse(raw) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("expms_token");
    if (!token) {
      setLoading(false);
      return;
    }
    client
      .get("/auth/me")
      .then((res) => {
        setUser(res.data);
        localStorage.setItem("expms_user", JSON.stringify(res.data));
      })
      .catch(() => {
        localStorage.removeItem("expms_token");
        localStorage.removeItem("expms_user");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(username, password) {
    const form = new URLSearchParams();
    form.append("username", username);
    form.append("password", password);
    const res = await client.post("/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    localStorage.setItem("expms_token", res.data.access_token);
    const me = await client.get("/auth/me");
    localStorage.setItem("expms_user", JSON.stringify(me.data));
    setUser(me.data);
    return me.data;
  }

  function logout() {
    localStorage.removeItem("expms_token");
    localStorage.removeItem("expms_user");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
