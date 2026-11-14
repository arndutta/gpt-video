import { Boxes, ChartNoAxesCombined, ClipboardCheck, FlaskConical, History, LayoutDashboard, MessageSquare } from 'lucide-react';

export const navigation = [
  { to: '/', label: 'Overview', description: 'Your pricing workspace at a glance', icon: LayoutDashboard, group: 'Workspace' },
  { to: '/catalog', label: 'Product catalog', description: 'Explore products, current prices, and constraints', icon: Boxes, group: 'Workspace' },
  { to: '/runs', label: 'Pricing runs', description: 'Create an analysis or revisit a run', icon: ChartNoAxesCombined, group: 'Workspace' },
  { to: '/review', label: 'Review queue', description: 'Inspect recommendations and decision evidence', icon: ClipboardCheck, group: 'Decisions' },
  { to: '/simulation', label: 'Scenario lab', description: 'Compare prices and explore uncertain outcomes', icon: FlaskConical, group: 'Decisions' },
  { to: '/audit', label: 'Audit trail', description: 'Follow every recorded decision and outcome', icon: History, group: 'Intelligence' },
  { to: '/discovery', label: 'Ask the evidence', description: 'Ask questions grounded in your documents', icon: MessageSquare, group: 'Intelligence' },
];
