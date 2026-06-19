import { createContext, useContext, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { isBroken } from "./regressions.js";

export const DEMO_EMAIL = "demo@nimbus.test";
export const DEMO_PASSWORD = "holo-qa-1";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => sessionStorage.getItem("nimbus-user"));

  function login(email, password) {
    if (email.trim().toLowerCase() !== DEMO_EMAIL || password !== DEMO_PASSWORD) {
      return false;
    }
    // auth-redirect-loop: report success but never persist the session, so the
    // route guard bounces the user straight back to /login.
    if (!isBroken("auth-redirect-loop")) {
      sessionStorage.setItem("nimbus-user", email.trim().toLowerCase());
      setUser(email.trim().toLowerCase());
    }
    return true;
  }

  function logout() {
    sessionStorage.removeItem("nimbus-user");
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

export function RequireAuth({ children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return children;
}
