import { useCallback, useEffect, useState } from 'react';
import { Boxes, ChartNoAxesCombined, CircleHelp, ClipboardCheck, FlaskConical, History, Layers3, LayoutDashboard, MessageSquare, Moon, Settings2, ShieldAlert, Sun } from 'lucide-react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { api } from '../api/client';
import type { Health } from '../api/types';
import { CatalogPage } from '../features/CatalogPage';
import { OverviewPage } from '../features/OverviewPage';
import { RunsPage } from '../features/RunsPage';
import { ScenarioPage } from '../features/ScenarioPage';
import { SettingsDrawer } from '../features/SettingsDrawer';
import { GroundingDrawer } from '../features/GroundingDrawer';
import { GlobalControls } from '../features/GlobalControls';
import { ReviewPage } from '../features/ReviewPage';
import { AuditPage } from '../features/AuditPage';
import { DiscoveryPage } from '../features/DiscoveryPage';
import '../features/operations.css';

const navigation = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/catalog', label: 'Product catalog', icon: Boxes },
  { to: '/runs', label: 'Pricing runs', icon: ChartNoAxesCombined },
  { to: '/review', label: 'Review queue', icon: ClipboardCheck },
  { to: '/simulation', label: 'Scenario lab', icon: FlaskConical },
  { to: '/audit', label: 'Audit trail', icon: History },
  { to: '/discovery', label: 'Ask the evidence', icon: MessageSquare },
];

export function App() {
  const [health, setHealth] = useState<Health>();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [groundingOpen, setGroundingOpen] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('pricing-theme') === 'dark');
  const location = useLocation();
  const refreshHealth = useCallback(() => { api<Health>('/health').then(setHealth).catch(() => setHealth(undefined)); }, []);
  const closeSettings = useCallback(() => setSettingsOpen(false), []);
  const closeGrounding = useCallback(() => setGroundingOpen(false), []);
  useEffect(() => { refreshHealth(); const timer = window.setInterval(refreshHealth, 10000); return () => window.clearInterval(timer); }, [refreshHealth]);
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; localStorage.setItem('pricing-theme', dark ? 'dark' : 'light'); }, [dark]);
  const page = navigation.find(item => item.to === location.pathname)?.label || 'Workspace';
  return <div className="app-layout">
    <aside className="sidebar">
      <Link to="/" className="brand"><span className="brand-icon"><Layers3 size={23} /></span><span>Retail pricing<small>DECISION WORKSPACE</small></span></Link>
      <div className="workspace-label">Workspace <span className="local-badge">Local</span></div>
      <nav aria-label="Main navigation">{navigation.map(item => <NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><item.icon size={19} />{item.label}</NavLink>)}</nav>
      <div className="sidebar-bottom">
        <button className="grounding-button" onClick={() => setGroundingOpen(true)}><Layers3 size={18} /><span>Knowledge & grounding<small>Documents & collections</small></span><CircleHelp size={15} /></button>
        <div className="workspace-person"><span className="avatar">PM</span><div>Pricing manager<small>Single-user workspace</small></div></div>
      </div>
    </aside>
    <div className="main-layout">
      <header className="global-header">
        <div className="breadcrumb">Workspace <span>/</span><strong>{page}</strong></div>
        <div className="header-controls">
          {health?.tls_verification_disabled && <span className="tls-warning" role="status"><ShieldAlert size={14} />TLS verification off</span>}
          <GlobalControls />
          <button className="icon-button" onClick={() => setDark(value => !value)} aria-label={`Switch to ${dark ? 'light' : 'dark'} theme`}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
          <button className="icon-button" onClick={() => setSettingsOpen(true)} aria-label="Open workspace settings"><Settings2 size={19} /></button>
        </div>
      </header>
      <main id="main-content"><Routes>
        <Route path="/" element={<OverviewPage health={health} refreshHealth={refreshHealth} />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/simulation" element={<ScenarioPage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/discovery" element={<DiscoveryPage />} />
        <Route path="*" element={<div className="panel empty-state"><h1>Page not found</h1><Link to="/">Return to overview</Link></div>} />
      </Routes></main>
      <footer className="workspace-footer"><span><span className={`status-dot ${health?.commerce?.status === 'ok' ? 'green' : ''}`} />{health?.commerce?.status === 'ok' ? 'Commerce connected' : 'Commerce connection unavailable'}</span><span>SKU-level pricing · Audited decisions</span></footer>
    </div>
    {settingsOpen && <SettingsDrawer onClose={closeSettings} onSaved={refreshHealth} />}
    {groundingOpen && <GroundingDrawer onClose={closeGrounding} />}
  </div>;
}
