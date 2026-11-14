import { useId } from 'react';
import { BarChart3, CheckCircle2, CloudLightning, Layers3, Leaf, TrendingDown, TrendingUp } from 'lucide-react';
import type { ScenarioRequest } from '../api/operations';

export function WorkflowChoice({ value, onChange, disabled }: { value: string; onChange: (value: string) => void; disabled?: boolean }) {
  const id = useId();
  const choices = [
    { value: 'quantitative_preview', label: 'Quantitative preview', description: 'Explore forecasts and uncertainty. No model gateway required; prices stay unchanged.', icon: BarChart3 },
    { value: 'grounded', label: 'Grounded pricing workflow', description: 'Add cited reasoning, policy checks, and mode-based review. Requires a gateway and indexed evidence.', icon: Layers3 },
  ];
  return <fieldset className="workflow-choices" disabled={disabled} onKeyDown={event => { if (event.key === 'Enter') event.preventDefault(); }}><legend>Workflow</legend><div className="workflow-choice-grid">{choices.map(choice => <label key={choice.value} className={`workflow-choice ${value === choice.value ? 'selected' : ''}`}><input type="radio" name={`${id}-workflow`} aria-label={choice.label} aria-describedby={`${id}-${choice.value}`} value={choice.value} checked={value === choice.value} onChange={() => onChange(choice.value)} /><span className="workflow-choice-icon"><choice.icon size={21} /></span><span><strong>{choice.label}</strong><small id={`${id}-${choice.value}`}>{choice.description}</small></span><CheckCircle2 className="workflow-choice-check" size={17} /></label>)}</div></fieldset>;
}

const stresses = [
  { value: 'none', label: 'Normal assumptions', description: 'Use the engine’s normal demand, competitor, and cost assumptions.', icon: Leaf },
  { value: 'demand_collapse', label: 'Demand collapse', description: 'Explore the engine’s lower-demand stress case.', icon: TrendingDown },
  { value: 'competitor_undercut', label: 'Competitor undercut', description: 'Explore the engine’s competitor-undercutting stress case.', icon: CloudLightning },
  { value: 'cost_spike', label: 'Cost spike', description: 'Explore the engine’s higher-cost stress case.', icon: TrendingUp },
] as const;

export function StressChoices({ value, onChange, disabled }: { value: ScenarioRequest['stress']; onChange: (value: ScenarioRequest['stress']) => void; disabled?: boolean }) {
  const id = useId();
  return <fieldset className="stress-choices" disabled={disabled} onKeyDown={event => { if (event.key === 'Enter') event.preventDefault(); }}><legend>Stress preset</legend><div className="stress-choice-grid">{stresses.map(choice => <label key={choice.value} className={`stress-choice ${value === choice.value ? 'selected' : ''}`}><input type="radio" name={`${id}-stress`} aria-label={choice.label} aria-describedby={`${id}-${choice.value}`} checked={value === choice.value} value={choice.value} onChange={() => onChange(choice.value)} /><choice.icon size={17} /><span>{choice.label}</span><small id={`${id}-${choice.value}`}>{choice.description}</small></label>)}</div></fieldset>;
}
