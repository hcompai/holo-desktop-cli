import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { DEMO_EMAIL, DEMO_PASSWORD, useAuth } from "../auth.jsx";
import { isBroken } from "../regressions.js";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  function onSubmit(event) {
    event.preventDefault();
    setError("");
    if (login(email, password)) {
      navigate("/dashboard");
      return;
    }
    setPassword("");
    // auth-silent-fail: swallow the error — the form just resets with no feedback.
    if (!isBroken("auth-silent-fail")) {
      setError("Incorrect email or password.");
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={onSubmit}>
        <h1>☁️ Nimbus Desk</h1>
        <p className="muted">Sign in to your support workspace</p>

        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          autoComplete="username"
        />

        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          autoComplete="current-password"
        />

        {error && (
          <div className="form-error" role="alert" data-testid="login-error">
            {error}
          </div>
        )}

        <button className="btn btn-primary" type="submit" disabled={!email || !password}>
          Sign in
        </button>

        <p className="muted demo-hint">
          Demo credentials: {DEMO_EMAIL} / {DEMO_PASSWORD}
        </p>
      </form>
    </div>
  );
}
