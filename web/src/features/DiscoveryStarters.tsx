import { ArrowUpRight, ClipboardCheck, FileSearch, ShieldCheck } from 'lucide-react';

const starters = [
  { title: 'Understand the policy', icon: ShieldCheck, question: 'Which pricing policy constraints should I review before changing a price?' },
  { title: 'Explore decision bands', icon: ClipboardCheck, question: 'How do Auto-approve, Review, and Escalate bands affect human review?' },
  { title: 'Find the evidence', icon: FileSearch, question: 'What evidence is required to explain and validate a pricing recommendation?' },
];

export function DiscoveryStarters({ onChoose, disabled }: { onChoose: (question: string) => void; disabled: boolean }) {
  return <div className="discovery-starters"><div className="discovery-starter-heading"><strong>A good question is a good starting point.</strong><span>Choose one to edit before sending.</span></div><div className="discovery-starter-grid">{starters.map(item => <button type="button" key={item.title} disabled={disabled} onClick={() => onChoose(item.question)}><item.icon size={20} /><strong>{item.title}</strong><span>{item.question}</span><ArrowUpRight size={14} /></button>)}</div></div>;
}
