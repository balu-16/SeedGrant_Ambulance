/**
 * Login — two-panel layout mirroring reference/LoginPage.png: left gradient
 * illustration panel (ambulance icon, product name, tagline), right form card
 * (email/password fields, primary gradient button, error line, admin-provided
 * credentials note). On success the user lands on their role's dashboard.
 */

import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/app/auth-context";
import { homeFor } from "@/app/nav";
import { ApiError } from "@/services/api";
import { Button, Field, Icon } from "@/components/ui";
import type { AuthUser } from "@/types/api";

const FEATURES: { icon: string; text: string }[] = [
  { icon: "traffic", text: "Green corridors for emergency vehicles" },
  { icon: "monitoring", text: "Live junction monitoring & manual override" },
  { icon: "local_shipping", text: "Hospital fleet and driver management" },
];

export function LoginPage() {
  const { user, booting, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Already signed in → straight to the dashboard.
  if (!booting && user) {
    return <Navigate to={homeFor(user.role)} replace />;
  }

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    if (!email.trim() || !password) {
      setError("Enter your email and password to continue.");
      return;
    }
    setBusy(true);
    (async () => {
      let signedIn: AuthUser;
      try {
        signedIn = await login(email, password);
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : "Could not sign in — please try again.",
        );
        setBusy(false);
        return;
      }
      const from = location.state?.from;
      navigate(
        // reject protocol-relative URLs ("//evil.com") as well as non-paths
        typeof from === "string" && from.startsWith("/") && !from.startsWith("//")
          ? from
          : homeFor(signedIn.role),
        { replace: true },
      );
    })();
  };

  return (
    <div className="login">
      <div className="login-hero">
        <span className="login-hero-bubble">
          <Icon name="emergency" size={52} color="var(--white)" />
        </span>
        <div>
          <div className="login-hero-title">SeedGrant Admin</div>
          <div className="login-hero-subtitle">
            Emergency traffic priority system
          </div>
        </div>
        <div className="login-hero-features">
          {FEATURES.map((f) => (
            <div className="login-hero-feature" key={f.icon}>
              <Icon name={f.icon} size={22} color="var(--blue-light)" />
              {f.text}
            </div>
          ))}
        </div>
        <div className="login-hero-tagline">
          <span className="login-hero-tagline-top">Every Second Counts</span>
          <span>──────── ︿ ────────</span>
          <span className="login-hero-tagline-bottom">
            Safe Roads. Healthy Lives.
          </span>
        </div>
      </div>

      <div className="login-panel">
        <form className="card login-card" onSubmit={onSubmit} noValidate>
          <div>
            <h1 className="login-title">Portal Login</h1>
            <p className="login-subtitle">
              Sign in to the SeedGrant control portal
            </p>
          </div>

          <div className="login-fields">
            <Field
              label="Email"
              icon="mail"
              type="email"
              name="email"
              autoComplete="username"
              placeholder="you@hospital.org"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Field
              label="Password"
              icon="lock"
              password
              name="password"
              autoComplete="current-password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && (
            <div className="login-error" role="alert">
              <Icon name="error" size={18} color="var(--red)" />
              {error}
            </div>
          )}

          <Button
            type="submit"
            title="Login"
            icon="arrow_forward"
            block
            loading={busy}
          />

          <div className="login-note">
            <span className="login-note-icon">
              <Icon name="verified_user" size={20} color="var(--blue)" />
            </span>
            <span>
              <span className="login-note-title">
                Credentials are provided by your administrator.
              </span>
              <span className="login-note-body">
                Portal accounts (ADMIN, HOSPITAL, POLICE) are created by the
                SeedGrant admin — there is no self-signup. Drivers use the
                mobile app.
              </span>
            </span>
          </div>

          <div className="login-footer">Need help? Contact your hospital admin.</div>
        </form>
      </div>
    </div>
  );
}
