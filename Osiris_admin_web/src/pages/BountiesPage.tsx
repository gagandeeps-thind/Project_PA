/* ───────────────────────────────────────────────────────────
 *  Bounties Page
 * ─────────────────────────────────────────────────────────── */
import { useEffect, useState, type FormEvent } from "react";
import {
  MapPin,
  Plus,
  Crosshair,
  Gem,
  Zap,
  Target,
} from "lucide-react";
import { getNearbyBounties, createBounty } from "../api/client";
import type { Bounty, CreateBountyPayload } from "../api/types";
import { TableSkeleton } from "../components/Skeleton";

/* Bedford, NS coordinates */
const BEDFORD_LAT = 44.7309;
const BEDFORD_LNG = -63.6568;
const SEARCH_RADIUS_KM = 500;

const emptyForm: CreateBountyPayload = {
  title: "",
  description: "",
  bounty_type: "daily",
  completions_remaining: 100,
  radius_m: 500,
  target_lat: BEDFORD_LAT,
  target_lng: BEDFORD_LNG,
  xp_reward: 50,
  crystal_reward: 10,
};

export default function BountiesPage() {
  const [bounties, setBounties] = useState<Bounty[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<CreateBountyPayload>({ ...emptyForm });
  const [submitting, setSubmitting] = useState(false);

  const fetchBounties = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getNearbyBounties(
        BEDFORD_LAT,
        BEDFORD_LNG,
        SEARCH_RADIUS_KM
      );
      setBounties(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load bounties");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBounties();
  }, []);

  const handleCreate = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await createBounty(form);
      setForm({ ...emptyForm });
      setShowForm(false);
      await fetchBounties();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create bounty");
    } finally {
      setSubmitting(false);
    }
  };

  const updateField = <K extends keyof CreateBountyPayload>(
    key: K,
    value: CreateBountyPayload[K]
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const typeBadge = (type: string) => {
    switch (type) {
      case "daily":
        return <span className="badge badge-cyan">Daily</span>;
      case "weekly":
        return <span className="badge badge-purple">Weekly</span>;
      case "special":
        return <span className="badge badge-warning">Special</span>;
      default:
        return <span className="badge badge-cyan">{type}</span>;
    }
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Bounty Management</h2>
        <p>Create, view, and manage world bounties</p>
      </div>

      <button className="btn-create" onClick={() => setShowForm(!showForm)}>
        <Plus size={18} />
        Create Daily Bounty
      </button>

      {/* Create Form */}
      {showForm && (
        <form className="form-card" onSubmit={handleCreate}>
          <h3
            className="section-title"
            style={{ marginBottom: 20 }}
          >
            New Bounty
          </h3>

          <div className="form-group">
            <label className="form-label">Title</label>
            <input
              className="form-input"
              placeholder="Morning Run Challenge"
              value={form.title}
              onChange={(e) => updateField("title", e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Description</label>
            <input
              className="form-input"
              placeholder="Complete a 2km run near the waterfront"
              value={form.description}
              onChange={(e) => updateField("description", e.target.value)}
              required
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Bounty Type</label>
              <select
                className="form-input"
                value={form.bounty_type}
                onChange={(e) => updateField("bounty_type", e.target.value)}
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="special">Special</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Completions Remaining</label>
              <input
                className="form-input"
                type="number"
                min={1}
                value={form.completions_remaining}
                onChange={(e) =>
                  updateField("completions_remaining", Number(e.target.value))
                }
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Radius (metres)</label>
              <input
                className="form-input"
                type="number"
                min={50}
                value={form.radius_m}
                onChange={(e) =>
                  updateField("radius_m", Number(e.target.value))
                }
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">XP Reward</label>
              <input
                className="form-input"
                type="number"
                min={0}
                value={form.xp_reward}
                onChange={(e) =>
                  updateField("xp_reward", Number(e.target.value))
                }
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Crystal Reward</label>
              <input
                className="form-input"
                type="number"
                min={0}
                value={form.crystal_reward}
                onChange={(e) =>
                  updateField("crystal_reward", Number(e.target.value))
                }
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Target Lat</label>
              <input
                className="form-input"
                type="number"
                step="0.0001"
                value={form.target_lat}
                onChange={(e) =>
                  updateField("target_lat", Number(e.target.value))
                }
                required
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Target Lng</label>
              <input
                className="form-input"
                type="number"
                step="0.0001"
                value={form.target_lng}
                onChange={(e) =>
                  updateField("target_lng", Number(e.target.value))
                }
                required
              />
            </div>
            <div />
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn-cancel"
              onClick={() => {
                setShowForm(false);
                setForm({ ...emptyForm });
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-submit"
              disabled={submitting}
            >
              {submitting ? "Creating…" : "Create Bounty"}
            </button>
          </div>
        </form>
      )}

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <TableSkeleton />
      ) : bounties.length === 0 ? (
        <div className="empty-state">
          <MapPin size={48} />
          <p>No bounties found in the area.</p>
        </div>
      ) : (
        <div className="bounty-grid">
          {bounties.map((b, i) => (
            <div
              className="bounty-card"
              key={b.id}
              style={{ animationDelay: `${i * 0.05}s` }}
            >
              <div className="bounty-card-header">
                <div className="bounty-card-title">{b.title}</div>
                <div style={{ display: "flex", gap: 6 }}>
                  {typeBadge(b.bounty_type)}
                  {b.is_active ? (
                    <span className="badge badge-success">Active</span>
                  ) : (
                    <span className="badge badge-error">Inactive</span>
                  )}
                </div>
              </div>

              <div className="bounty-card-desc">{b.description}</div>

              <div className="bounty-card-stats">
                <div className="bounty-stat">
                  <div className="bounty-stat-label">
                    <Target size={12} style={{ marginRight: 4, verticalAlign: "middle" }} />
                    Completions
                  </div>
                  <div className="bounty-stat-value">
                    {b.completions_count} / {b.completions_remaining + b.completions_count}
                  </div>
                </div>

                <div className="bounty-stat">
                  <div className="bounty-stat-label">
                    <Crosshair size={12} style={{ marginRight: 4, verticalAlign: "middle" }} />
                    Radius
                  </div>
                  <div className="bounty-stat-value">{b.radius_m}m</div>
                </div>

                <div className="bounty-stat">
                  <div className="bounty-stat-label">
                    <Zap size={12} style={{ marginRight: 4, verticalAlign: "middle" }} />
                    XP Reward
                  </div>
                  <div className="bounty-stat-value" style={{ color: "var(--accent-cyan)" }}>
                    {b.xp_reward}
                  </div>
                </div>

                <div className="bounty-stat">
                  <div className="bounty-stat-label">
                    <Gem size={12} style={{ marginRight: 4, verticalAlign: "middle" }} />
                    Crystals
                  </div>
                  <div className="bounty-stat-value" style={{ color: "var(--accent-purple)" }}>
                    {b.crystal_reward}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
