import { AlertCircle, ArrowRight, LoaderCircle, X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

export function ErrorNotice({ message }: { message: string }) {
  return <div className="notice error" role="alert"><AlertCircle size={18} /><span>{message}</span></div>;
}

export function Loading({ label = 'Loading workspace…' }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={20} />{label}</div>;
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children: ReactNode }) {
  return <div className="empty-state">{icon}<h3>{title}</h3><div>{children}</div></div>;
}

export function PageHeading({ eyebrow, title, children, action }: { eyebrow: string; title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{children}</p></div>{action}</div>;
}

export function Status({ status }: { status: string }) {
  const good = ['ok', 'completed', 'healthy'].includes(status);
  const bad = ['failed', 'unavailable', 'degraded', 'interrupted'].includes(status);
  return <span className={`status ${good ? 'success' : bad ? 'danger' : 'neutral'}`}><span className="status-dot" />{status.replaceAll('_', ' ')}</span>;
}

export function Drawer({ title, subtitle, onClose, children }: { title: string; subtitle?: string; onClose: () => void; children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panel.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key !== 'Tab') return;
      const elements = panel.current?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea, [tabindex="0"]');
      if (!elements?.length) return;
      const first = elements[0], last = elements[elements.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = oldOverflow; previous?.focus(); };
  }, [onClose]);
  return <div className="drawer-backdrop" onClick={onClose}><div ref={panel} className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabIndex={-1} onClick={event => event.stopPropagation()}><div className="drawer-heading"><div><h2 id="drawer-title">{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" aria-label="Close panel" onClick={onClose}><X size={20} /></button></div>{children}</div></div>;
}

export function PreviewNotice() {
  return <div className="preview-notice"><span className="preview-label">QUANTITATIVE PREVIEW</span><span>Explore deterministic forecasts. Grounded agents, approval, and price execution are not enabled.</span><ArrowRight size={16} /></div>;
}
