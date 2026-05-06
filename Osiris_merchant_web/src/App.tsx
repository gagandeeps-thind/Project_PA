import React, { useState, useEffect } from 'react';
import { Shield, Activity, MapPin, Database, LogOut } from 'lucide-react';
import { loginMerchant, fetchBounties } from './api';
import './index.css';

interface Bounty {
  id: number;
  title: string;
  description: string;
  bounty_type: string;
  completions_remaining: number;
  radius_m: number;
}

function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('merchant_token'));
  const [merchantData, setMerchantData] = useState<any>(null);
  
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [bounties, setBounties] = useState<Bounty[]>([]);

  useEffect(() => {
    const savedMerchant = localStorage.getItem('merchant_data');
    if (savedMerchant) {
      setMerchantData(JSON.parse(savedMerchant));
    }
  }, []);

  useEffect(() => {
    if (token && merchantData) {
      loadDashboard();
    }
  }, [token, merchantData]);

  const loadDashboard = async () => {
    try {
      const data = await fetchBounties(merchantData.id);
      setBounties(data);
    } catch (err) {
      console.error("Failed to load bounties", err);
      // If token expired
      if (err.response?.status === 401 || err.response?.status === 403) {
        handleLogout();
      }
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await loginMerchant(email, password);
      if (data.role !== 'merchant') {
        setError('This portal is for merchants only.');
        setLoading(false);
        return;
      }
      localStorage.setItem('merchant_token', data.access_token);
      localStorage.setItem('merchant_data', JSON.stringify(data));
      setToken(data.access_token);
      setMerchantData(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Login failed. Check credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('merchant_token');
    localStorage.removeItem('merchant_data');
    setToken(null);
    setMerchantData(null);
  };

  if (!token || !merchantData) {
    return (
      <div className="app-layout" style={{ alignItems: 'center', justifyContent: 'center' }}>
        <div className="glass-panel" style={{ padding: '40px', width: '100%', maxWidth: '400px' }}>
          <div style={{ textAlign: 'center', marginBottom: '32px' }}>
            <Shield size={48} color="var(--accent-primary)" style={{ marginBottom: '16px' }} />
            <h2>Osiris Connect</h2>
            <p className="text-secondary" style={{ marginTop: '8px' }}>Merchant Analytics Portal</p>
          </div>

          <form onSubmit={handleLogin}>
            <div className="input-group">
              <label className="input-label">Email Address</label>
              <input 
                type="email" 
                className="input-field" 
                placeholder="partner@business.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            
            <div className="input-group">
              <label className="input-label">Password</label>
              <input 
                type="password" 
                className="input-field" 
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            {error && (
              <div style={{ color: 'var(--error)', fontSize: '0.875rem', marginBottom: '16px' }}>
                {error}
              </div>
            )}

            <button 
              type="submit" 
              className="btn btn-primary" 
              style={{ width: '100%', marginTop: '8px' }}
              disabled={loading}
            >
              {loading ? 'Authenticating...' : 'Secure Login'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <div className="sidebar">
        <div style={{ padding: '32px 24px', borderBottom: '1px solid var(--border-light)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Shield size={28} color="var(--accent-primary)" />
            <h3 style={{ fontSize: '1.25rem' }} className="text-gradient">Osiris</h3>
          </div>
          <div className="badge badge-success" style={{ marginTop: '12px' }}>Connected</div>
        </div>
        
        <div style={{ padding: '24px', flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div className="btn btn-secondary" style={{ justifyContent: 'flex-start', background: 'rgba(255,255,255,0.05)', borderColor: 'var(--accent-primary)' }}>
            <Activity size={18} /> Analytics
          </div>
          <div className="btn btn-secondary" style={{ justifyContent: 'flex-start', border: 'none' }}>
            <Database size={18} /> Bounties
          </div>
        </div>

        <div style={{ padding: '24px', borderTop: '1px solid var(--border-light)' }}>
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>Logged in as</div>
            <div style={{ fontWeight: 600 }}>{merchantData.name}</div>
          </div>
          <button onClick={handleLogout} className="btn btn-secondary" style={{ width: '100%', justifyContent: 'flex-start' }}>
            <LogOut size={18} /> Disconnect
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="main-content">
        <div className="container animate-fade-in">
          <header style={{ marginBottom: '40px' }}>
            <h1 style={{ fontSize: '2.5rem', marginBottom: '8px' }}>Dashboard Overview</h1>
            <p className="text-secondary">Welcome back to the merchant portal. View your active chest engagements below.</p>
          </header>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px', marginBottom: '40px' }}>
            <div className="glass-card delay-100">
              <div style={{ color: 'var(--text-secondary)', marginBottom: '8px', fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Active Bounties</div>
              <div style={{ fontSize: '2.5rem', fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--accent-primary)' }}>
                {bounties.length}
              </div>
            </div>
            
            <div className="glass-card delay-200">
              <div style={{ color: 'var(--text-secondary)', marginBottom: '8px', fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Completions Remaining</div>
              <div style={{ fontSize: '2.5rem', fontFamily: 'var(--font-display)', fontWeight: 700, color: 'var(--success)' }}>
                {bounties.reduce((acc, curr) => acc + curr.completions_remaining, 0)}
              </div>
            </div>
          </div>

          <h3>Active Chests</h3>
          <div style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {bounties.length === 0 ? (
              <div className="glass-card delay-300" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                No active bounties found. Connect with an admin to sponsor a chest.
              </div>
            ) : (
              bounties.map((bounty, i) => (
                <div key={bounty.id} className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', animationDelay: `${300 + (i * 100)}ms` }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <h4 style={{ fontSize: '1.25rem', margin: 0 }}>{bounty.title}</h4>
                      <span className="badge badge-success">{bounty.bounty_type}</span>
                    </div>
                    <p style={{ color: 'var(--text-secondary)', margin: 0 }}>{bounty.description}</p>
                    <div style={{ display: 'flex', gap: '16px', marginTop: '12px', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><MapPin size={14} /> Radius: {bounty.radius_m}m</span>
                    </div>
                  </div>
                  
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>{bounty.completions_remaining}</div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>remaining</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
