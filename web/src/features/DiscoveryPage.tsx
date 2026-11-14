import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { BookOpenCheck, MessageSquare, Send } from 'lucide-react';
import { api, errorMessage } from '../api/client';
import { EmptyState, ErrorNotice, Loading, PageHeading } from '../components/Common';
import { EvidenceSources } from '../components/EvidenceSources';
import { StructuredEvidence } from '../components/Forecast';
import { DiscoveryStarters } from './DiscoveryStarters';

type Answer = { answer?: string; response?: string; summary?: string; citations?: unknown; sources?: unknown; [key: string]: unknown };

export function DiscoveryPage() {
  const [query, setQuery] = useState('');
  const question = useRef<HTMLTextAreaElement>(null);
  function chooseQuestion(value: string) { setQuery(value); question.current?.focus(); }
  const [answer, setAnswer] = useState<Answer>();
  const [answeredQuery, setAnsweredQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setAnswer(undefined); setAnsweredQuery(query);
    try { setAnswer(await api<Answer>('/discovery/chat', { method: 'POST', body: JSON.stringify({ query }) })); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }
  return <div className="chat-layout"><PageHeading eyebrow="GROUNDED DISCOVERY" title="Ask the evidence">Explore pricing policy and recommendation evidence through a cited, read-only conversation.</PageHeading><DiscoveryStarters onChoose={chooseQuestion} disabled={busy} /><section className="panel"><form className="panel-body form-stack" onSubmit={submit}><label>Question<textarea ref={question} disabled={busy} value={query} onChange={event => setQuery(event.target.value)} required minLength={3} maxLength={4000} placeholder="Which policy considerations should I review before changing a price?" /></label><button className="button primary" disabled={busy || query.trim().length < 3} type="submit"><Send size={15} />{busy ? 'Consulting evidence…' : 'Ask a question'}</button><p className="small muted">This interface can explain evidence. Price decisions stay in the review and execution workflow.</p></form>{error && <div className="panel-body"><ErrorNotice message={error} /></div>}{busy ? <Loading label="Retrieving current sources and generating a cited answer…" /> : answer ? <div className="chat-response"><div className="discovery-answer-heading"><BookOpenCheck size={17} />Evidence response</div><div className="discovery-answer-query"><span>Answer to</span><p>{answeredQuery}</p></div><p>{answer.answer || answer.response || answer.summary}</p>{!answer.answer && !answer.response && !answer.summary && <StructuredEvidence value={answer} />}<h3 style={{ margin: '22px 0 13px' }}>Cited evidence</h3><EvidenceSources value={answer} /></div> : !error && <EmptyState icon={<MessageSquare size={31} />} title="Start with a pricing question"><p>Answers require a configured gateway and currently indexed grounding sources.</p></EmptyState>}</section></div>;
}
