import { useEffect, useId, useRef, useState } from 'react';
import { ArrowUpRight, CornerDownLeft, Layers3, Moon, Search, Settings2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Drawer } from '../components/Common';
import { navigation } from './navigation';

type Props = { onClose: () => void; onSettings: () => void; onGrounding: () => void; onTheme: () => void };

export function WorkspaceCommands({ onClose, onSettings, onGrounding, onTheme }: Props) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const navigate = useNavigate();
  const commands = [
    ...navigation.map(item => ({ ...item, run: () => navigate(item.to) })),
    { label: 'Workspace settings', description: 'Configure the gateway and pricing policy', icon: Settings2, group: 'Actions', run: onSettings },
    { label: 'Knowledge & grounding', description: 'Upload documents and inspect evidence', icon: Layers3, group: 'Actions', run: onGrounding },
    { label: 'Toggle color theme', description: 'Switch between light and dark', icon: Moon, group: 'Actions', run: onTheme },
  ].filter(item => `${item.label} ${item.description}`.toLowerCase().includes(query.trim().toLowerCase()));
  const selected = Math.min(active, Math.max(0, commands.length - 1));
  useEffect(() => { document.getElementById(`${listId}-${selected}`)?.scrollIntoView?.({ block: 'nearest' }); }, [listId, selected, query]);
  function choose(index: number) { const command = commands[index]; if (command) { onClose(); command.run(); } }
  return <Drawer title="Find your next move" subtitle="Navigate your workspace without leaving the keyboard." onClose={onClose} className="command-backdrop" initialFocusRef={input}>
    <div className="command-search"><Search size={21} /><input ref={input} role="combobox" aria-label="Search workspace" aria-expanded="true" aria-controls={listId} aria-autocomplete="list" aria-activedescendant={commands.length ? `${listId}-${selected}` : undefined} placeholder="Search pages and actions…" value={query} onChange={event => { setQuery(event.target.value); setActive(0); }} onKeyDown={event => {
      if (event.nativeEvent.isComposing) return;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setActive(value => commands.length ? (value + (event.key === 'ArrowDown' ? 1 : -1) + commands.length) % commands.length : 0); }
      if (event.key === 'Enter') { event.preventDefault(); choose(selected); }
    }} /><kbd>esc</kbd></div>
    <div className="command-results" id={listId} role="listbox" aria-label="Workspace destinations">{commands.length ? commands.map((item, index) => <div role="option" aria-selected={selected === index} id={`${listId}-${index}`} key={item.label} className={`command-option ${selected === index ? 'selected' : ''}`} onMouseMove={() => setActive(index)} onClick={() => choose(index)}><span className="command-icon"><item.icon size={19} /></span><span><strong>{item.label}</strong><small>{item.description}</small></span><ArrowUpRight size={16} /></div>) : <div className="command-empty">No matching pages. Try “scenario”, “catalog”, or “settings”.</div>}</div>
    <div className="command-footer"><span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span><span><CornerDownLeft size={13} /> to open</span><span>Navigation & settings only</span></div>
  </Drawer>;
}
