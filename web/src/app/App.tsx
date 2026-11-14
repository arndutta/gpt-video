import { useCallback, useEffect, useState } from 'react';
import { ArrowUpRight, ChevronLeft, ChevronRight, Command, Layers3, Moon, RefreshCw, Search, Settings2, ShieldAlert, ShieldCheck, Sun } from 'lucide-react';
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
import { navigation } from './navigation';
import { WorkspaceCommands } from './WorkspaceCommands';
import '../features/operations.css';

export function App() {
  const [health, setHealth] = useState<Health>();
  const [healthChecked, setHealthChecked] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [groundingOpen, setGroundingOpen] = useState(false);
  const [commandsOpen, setCommandsOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem('pricing-theme') === 'dark');
  const location = useLocation();
  const refreshHealth = useCallback(() => { api<Health>('/health').then(setHealth).catch(() => setHealth(undefined)).finally(() => setHealthChecked(true)); }, []);
  const closeSettings = useCallback(() => setSettingsOpen(false), []);
  const closeGrounding = useCallback(() => setGroundingOpen(false), []);
  const closeCommands = useCallback(() => setCommandsOpen(false), []);
  const openSettings = useCallback(() => setSettingsOpen(true), []);
  const openGrounding = useCallback(() => setGroundingOpen(true), []);
  const toggleTheme = useCallback(() => setDark(value => !value), []);
  useEffect(() => { refreshHealth(); const timer = window.setInterval(refreshHealth, 10000); return () => window.clearInterval(timer); }, [refreshHealth]);
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; localStorage.setItem('pricing-theme', dark ? 'dark' : 'light'); }, [dark]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.isComposing) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && (commandsOpen || !document.querySelector('[role="dialog"]'))) { event.preventDefault(); if (!event.repeat) setCommandsOpen(value => !value); }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [commandsOpen]);
  const page = navigation.find(item => item.to === location.pathname)?.label || 'Workspace';
  useEffect(() => { document.title = `${page} · Retail pricing`; }, [page]);
  return <div className={`app-layout ${collapsed ? 'rail-collapsed' : ''}`}>
    <a className="skip-link" href="#main-content">Skip to main content</a>
    <aside className="sidebar" aria-label="Workspace sidebar">
      <Link to="/" className="brand" aria-label="Retail pricing home"><span className="brand-icon"><Layers3 size={24} /></span><span className="brand-name">Retail pricing<small>DECISION WORKSPACE</small></span></Link>
      <button className="rail-toggle" aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} aria-expanded={!collapsed} onClick={() => setCollapsed(value => !value)}>{collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}</button>
      <nav aria-label="Main navigation">{['Workspace', 'Decisions', 'Intelligence'].map(group => <div className="nav-group" key={group}><div className="workspace-label">{group}{group === 'Workspace' && <span className="local-badge">Local</span>}</div>{navigation.filter(item => item.group === group).map(item => <NavLink key={item.to} to={item.to} end={item.to === '/'} title={item.label} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><item.icon size={19} /><span className="nav-label">{item.label}</span><span className="nav-active-dot" /></NavLink>)}</div>)}</nav>
      <div className="sidebar-bottom">
        <div className="sidebar-note"><ShieldCheck size={20} /><strong>Confidence in every decision.</strong><p>Evidence, compliance, and human review in one workspace.</p></div>
        <button className="grounding-button" onClick={openGrounding} title="Knowledge & grounding"><Layers3 size={18} /><span>Knowledge & grounding<small>Documents & collections</small></span><ArrowUpRight size={15} /></button>
        <div className="workspace-person"><span className="avatar">PM</span><div>Pricing manager<small>Local workspace</small></div><span className="person-status" /></div>
      </div>
    </aside>
    <div className="main-layout">
      <header className="global-header">
        <div className="header-top"><div className="breadcrumb">Workspace <ChevronRight size={13} /><strong>{page}</strong></div><div className="header-utilities"><button className="workspace-search" onClick={() => setCommandsOpen(true)} aria-label="Open workspace search"><Search size={16} /><span>Jump to anything…</span><kbd><Command size={11} />K</kbd></button><button className="icon-button" onClick={toggleTheme} aria-label={`Switch to ${dark ? 'light' : 'dark'} theme`}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button><button className="icon-button" onClick={openSettings} aria-label="Open workspace settings"><Settings2 size={19} /></button></div></div>
        <div className="header-bottom"><span className={`service-pill ${health?.commerce?.status === 'ok' ? 'connected' : ''}`}><span className="status-dot" />{health?.commerce?.status === 'ok' ? 'Commerce connected' : health ? 'Commerce unavailable' : healthChecked ? 'Status unavailable' : 'Connecting to services'}{healthChecked && !health && <button className="service-retry" onClick={refreshHealth} aria-label="Retry service check" title="Retry service check"><RefreshCw size={12} /></button>}</span><div className="header-controls">
          {health?.tls_verification_disabled && <span className="tls-warning" role="status"><ShieldAlert size={14} />TLS verification off</span>}
          <GlobalControls />
        </div></div>
      </header>
      <main id="main-content" tabIndex={-1}><div className="route-content" key={location.pathname}><Routes>
        <Route path="/" element={<OverviewPage health={health} refreshHealth={refreshHealth} />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/simulation" element={<ScenarioPage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/discovery" element={<DiscoveryPage />} />
        <Route path="*" element={<div className="panel empty-state"><h1>Page not found</h1><Link to="/">Return to overview</Link></div>} />
      </Routes></div></main>
      <footer className="workspace-footer"><span><ShieldCheck size={13} />Evidence-led pricing. Audited decisions.</span><span>Retail pricing workspace <span className="footer-dot">·</span> Local</span></footer>
    </div>
    {settingsOpen && <SettingsDrawer onClose={closeSettings} onSaved={refreshHealth} />}
    {groundingOpen && <GroundingDrawer onClose={closeGrounding} />}
    {commandsOpen && <WorkspaceCommands onClose={closeCommands} onSettings={openSettings} onGrounding={openGrounding} onTheme={toggleTheme} />}
  </div>;
}
