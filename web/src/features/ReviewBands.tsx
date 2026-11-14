import { CheckCircle2, Layers3, ShieldAlert, UserCheck } from 'lucide-react';
import { number } from '../api/client';
import type { ManagedRecommendation } from '../api/operations';

export function ReviewBands({ items, loaded, selected, onChange }: { items: ManagedRecommendation[]; loaded: boolean; selected: string; onChange: (band: string) => void }) {
  const bands = [
    { value: '', label: 'All loaded', icon: Layers3, description: 'Every loaded recommendation' },
    { value: 'escalate', label: 'Escalate', icon: ShieldAlert, description: 'Written human judgment required' },
    { value: 'review', label: 'Review', icon: UserCheck, description: 'Inspect before making a decision' },
    { value: 'auto_approve', label: 'Auto-approve', icon: CheckCircle2, description: 'Band eligibility; mode still applies' },
  ];
  return <div className="review-band-overview" role="group" aria-label="Filter loaded recommendations by band">{bands.map(band => <button key={band.value} className={`review-band-card ${band.value || 'all'} ${selected === band.value ? 'selected' : ''}`} aria-label={`Show ${band.label} recommendations`} aria-pressed={selected === band.value} onClick={() => onChange(band.value)}><span className="review-band-icon"><band.icon size={18} /></span><span className="review-band-value">{loaded ? number(band.value ? items.filter(item => item.band === band.value).length : items.length) : '—'}</span><strong>{band.label}</strong><small>{band.description}</small></button>)}</div>;
}
