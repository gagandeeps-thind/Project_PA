/* ───────────────────────────────────────────────────────────
 *  Login Page
 * ─────────────────────────────────────────────────────────── */
import { useState, type FormEvent } from "react";
import { Shield, Loader } from "lucide-react";
import { loginAdmin } from "../api/client";
import type { AdminUser } from "../api/types";

interface LoginPageProps {
  onLogin: (user: AdminUser, token: string) => void;
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await loginAdmin(email, password);
      const user: AdminUser = {
        id: res.id,
        name: res.name,
        email: res.email,
        role: res.role,
      };
      onLogin(user, res.access_token);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Login failed. Please check your credentials.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-header">
          <div className="login-icon">
            <Shield size={30} />
          </div>
          <h1>OSIRIS COMMAND</h1>
          <p>Admin Control Center</p>
        </div>

        {error && <div className="error-message">{error}</div>}

        <div className="form-group">
          <label className="form-label" htmlFor="email">
            Email Address
          </label>
          <input
            id="email"
            type="email"
            className="form-input"
            placeholder="admin@osiris.gg"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="form-input"
            placeholder="••••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? <Loader size={18} className="spin" /> : "Access Terminal"}
        </button>
      </form>
    </div>
  );
}
