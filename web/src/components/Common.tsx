import { AlertCircle, ArrowRight, LoaderCircle, X } from 'lucide-react';
import { useEffect, useId, useRef } from 'react';
import type { ReactNode, RefObject } from 'react';
import { createPortal } from 'react-dom';
import { focusableElements } from './focus';

export function ErrorNotice({ message }: { message: string }) {
  return <div className="notice error" role="alert"><AlertCircle size={18} /><span>{message}</span></div>;
}

export function Loading({ label = 'Loading workspace…' }: { label?: string }) {
  return <div className="loading" role="status"><span className="loading-label"><LoaderCircle className="spin" size={20} />{label}</span><span className="loading-skeleton" aria-hidden="true"><i /><i /><i /></span></div>;
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children: ReactNode }) {
  return <div className="empty-state">{icon}<h3>{title}</h3><div>{children}</div></div>;
}

export function PageHeading({ eyebrow, title, children, action }: { eyebrow: string; title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{children}</p></div>{action}</div>;
}

export function Status({ status }: { status: string }) {
  const good = ['ok', 'completed', 'healthy', 'passed', 'approved', 'applied', 'unchanged'].includes(status);
  const bad = ['failed', 'unavailable', 'degraded', 'interrupted', 'blocked', 'execution_rejected', 'unknown', 'stale'].includes(status);
  return <span className={`status ${good ? 'success' : bad ? 'danger' : 'neutral'}`}><span className="status-dot" />{status === 'unchanged' ? 'No change' : status.replaceAll('_', ' ')}</span>;
}

export function Drawer({ title, subtitle, onClose, children, className = '', initialFocusRef }: { title: string; subtitle?: string; onClose: () => void; children: ReactNode; className?: string; initialFocusRef?: RefObject<HTMLElement | null> }) {
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  const initialFocus = useRef(initialFocusRef);
  const titleId = useId();
  useEffect(() => { close.current = onClose; }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    (initialFocus.current?.current || panel.current)?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.isComposing || event.defaultPrevented) return;
      if (event.key === 'Escape') close.current();
      if (event.key !== 'Tab') return;
      const elements = panel.current ? focusableElements(panel.current) : [];
      if (!elements.length) { event.preventDefault(); panel.current?.focus(); return; }
      const first = elements[0], last = elements[elements.length - 1];
      const active = document.activeElement;
      const outside = !panel.current?.contains(active);
      if (event.shiftKey && (active === first || active === panel.current || outside)) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && (active === last || active === panel.current || outside)) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = oldOverflow; previous?.focus(); };
  }, []);
  const content = <div className={`drawer-backdrop ${className}`} onClick={onClose}><div ref={panel} className="drawer" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1} onClick={event => event.stopPropagation()}><div className="drawer-heading"><div><h2 id={titleId}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" aria-label="Close panel" onClick={onClose}><X size={20} /></button></div>{children}</div></div>;
  return typeof document === 'undefined' ? content : createPortal(content, document.body);
}

export function PreviewNotice() {
  return <div className="preview-notice"><span className="preview-label">QUANTITATIVE PREVIEW</span><span>Explore deterministic forecasts. Grounded agents, approval, and price execution are not enabled.</span><ArrowRight size={16} /></div>;
}
