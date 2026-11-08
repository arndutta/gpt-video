import { useCallback, useEffect, useState } from 'react';
import { Activity, Boxes, ChartNoAxesCombined, CircleHelp, FlaskConical, Layers3, LayoutDashboard, Moon, Settings2, ShieldAlert, ShieldCheck, Square, Sun } from 'lucide-react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { api } from '../api/client';
import type { Health } from '../api/types';
import { Drawer, PreviewNotice } from '../components/Common';
import { CatalogPage } from '../features/CatalogPage';
import { OverviewPage } from '../features/OverviewPage';
import { RunsPage } from '../features/RunsPage';
import { ScenarioPage } from '../features/ScenarioPage';
import { SettingsDrawer } from '../features/SettingsDrawer';

const navigation = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/catalog', label: 'Product catalog', icon: Boxes },
  { to: '/runs', label: 'Pricing runs', icon: ChartNoAxesCombined },
  { to: '/simulation', label: 'Scenario lab', icon: FlaskConical },
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
        <button className="grounding-button" onClick={() => setGroundingOpen(true)}><Layers3 size={18} /><span>Knowledge & grounding<small>Agent integration pending</small></span><CircleHelp size={15} /></button>
        <div className="workspace-person"><span className="avatar">PM</span><div>Pricing manager<small>Single-user workspace</small></div></div>
      </div>
    </aside>
    <div className="main-layout">
      <header className="global-header">
        <div className="breadcrumb">Workspace <span>/</span><strong>{page}</strong></div>
        <div className="header-controls">
          {health?.tls_verification_disabled && <span className="tls-warning" role="status"><ShieldAlert size={14} />TLS verification off</span>}
          <span className="llm-monitor" title="Quantitative previews do not call language models"><Activity size={15} />LLM idle<span className="monitor-divider" />No token spend</span>
          <span className="loop-state"><span className="status-dot" />Loop off</span>
          <div className="mode-indicator" title="Automation is not enabled in this foundation build"><ShieldCheck size={15} /><select aria-label="Operating mode" value="supervised" disabled><option value="supervised">Supervised</option></select></div>
          <button className="kill-button" disabled title="No automatic execution is enabled"><Square size={12} />Halt</button>
          <button className="icon-button" onClick={() => setDark(value => !value)} aria-label={`Switch to ${dark ? 'light' : 'dark'} theme`}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
          <button className="icon-button" onClick={() => setSettingsOpen(true)} aria-label="Open workspace settings"><Settings2 size={19} /></button>
        </div>
      </header>
      <main id="main-content"><PreviewNotice /><Routes>
        <Route path="/" element={<OverviewPage health={health} refreshHealth={refreshHealth} />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/simulation" element={<ScenarioPage />} />
        <Route path="*" element={<div className="panel empty-state"><h1>Page not found</h1><Link to="/">Return to overview</Link></div>} />
      </Routes></main>
      <footer className="workspace-footer"><span><span className={`status-dot ${health?.commerce?.status === 'ok' ? 'green' : ''}`} />{health?.commerce?.status === 'ok' ? 'Commerce connected' : 'Commerce connection unavailable'}</span><span>Local analysis · Prices are unchanged</span></footer>
    </div>
    {settingsOpen && <SettingsDrawer onClose={closeSettings} onSaved={refreshHealth} />}
    {groundingOpen && <Drawer title="Knowledge & grounding" subtitle="Evidence for future agent recommendations" onClose={closeGrounding}><div className="drawer-body"><div className="empty-state"><Layers3 size={35} /><h3>Grounding integration is pending</h3><p>Document ingestion, embedding statistics, and grounded agent reasoning will be added in the orchestration milestone.</p></div><div className="notice info">Current results are deterministic quantitative previews. They are not grounded AI recommendations and cannot approve or push prices.</div></div></Drawer>}
  </div>;
}
