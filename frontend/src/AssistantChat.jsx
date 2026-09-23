import { useEffect, useRef, useState } from 'react';
import { LoaderCircle, MessageCircleMore, Send, Sparkles, X } from 'lucide-react';
import { saveBackFrontError } from './lib/back-front-errors.js';
import { askAssistant } from './lib/api.js';

const SUGGESTIONS = ['Какие позиции критичные?', 'Почему нужен заказ?', 'Какая общая сумма?'];

export default function AssistantChat({ mode, available = true }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);
  const messagesRef = useRef(null);
  const buttonRef = useRef(null);
  const requestRef = useRef(null);

  useEffect(() => () => requestRef.current?.abort(), []);
  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);
  useEffect(() => { if (open) messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: 'smooth' }); }, [open, messages, pending, error]);

  function close() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  async function send(value = draft) {
    const question = value.trim();
    if (!question || requestRef.current || mode === 'demo' || !available) return;
    const history = messages.slice(-10).map(({ role, content }) => ({ role, content: content.slice(0, 1500) }));
    const controller = new AbortController();
    requestRef.current = controller;
    setMessages((previous) => [...previous, { role: 'user', content: question }]);
    setDraft('');
    setError('');
    setPending(true);
    try {
      const answer = await askAssistant({ question, history, signal: controller.signal });
      setMessages((previous) => [...previous, { role: 'assistant', content: answer }]);
    } catch (failure) {
      if (!controller.signal.aborted) {
        saveBackFrontError(failure, { mode: 'api', endpoint: '/assistant/chat' });
        setMessages((previous) => previous.slice(0, -1));
        setDraft(question);
        setError(failure.message);
      }
    } finally {
      if (!controller.signal.aborted) setPending(false);
      if (requestRef.current === controller) requestRef.current = null;
    }
  }

  return <div className="assistant-widget">
    {open && <section className="assistant-panel" aria-label="ИИ-помощник по закупкам"
      onKeyDown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); close(); } }}>
      <header className="assistant-header">
        <span className="assistant-symbol"><Sparkles size={20} aria-hidden="true" /></span>
        <span><strong>Помощник Ketnavr</strong><small>Вопросы по всему расчёту</small></span>
        <button type="button" className="assistant-close" onClick={close} aria-label="Закрыть помощника"><X size={19} /></button>
      </header>
      <div ref={messagesRef} className="assistant-messages" role="log" aria-live="polite" aria-relevant="additions text">
        <div className="assistant-bubble assistant-bubble-ai">Привет! Помогу разобраться с рекомендациями по закупкам. Спросите о приоритетах, товарах или сумме заказа.</div>
        {mode === 'demo' && <p className="assistant-hint">Сейчас открыты синтетические демоданные. Для диалога переключитесь на рабочие данные и настройте ИИ в backend.</p>}
        {messages.map((message, index) => <div key={index} className={`assistant-bubble assistant-bubble-${message.role === 'user' ? 'user' : 'ai'}`}>{message.content}</div>)}
        {pending && <div className="assistant-bubble assistant-bubble-ai assistant-thinking" role="status"><LoaderCircle size={16} className="spin" /> Думаю над ответом…</div>}
        {error && <p className="assistant-error" role="alert">{error}</p>}
        {!available && mode !== 'demo' && <p className="assistant-hint">Дождитесь загрузки расчёта, чтобы задать вопрос.</p>}
      </div>
      {mode !== 'demo' && messages.length === 0 && <div className="assistant-suggestions" aria-label="Примеры вопросов">
        {SUGGESTIONS.map((suggestion) => <button type="button" key={suggestion} disabled={pending || !available} onClick={() => send(suggestion)}>{suggestion}</button>)}
      </div>}
      <form className="assistant-compose" onSubmit={(event) => { event.preventDefault(); send(); }}>
        <label className="sr-only" htmlFor="assistant-question">Сообщение помощнику</label>
        <textarea id="assistant-question" ref={inputRef} rows="1" maxLength="1000" placeholder="Спросите о закупках…" value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(); } }}
          disabled={pending || mode === 'demo' || !available} />
        <button type="submit" aria-label="Отправить сообщение" disabled={!draft.trim() || pending || mode === 'demo' || !available}><Send size={18} /></button>
      </form>
      <p className="assistant-footnote">Ответ по всему расчёту, не текущим фильтрам. Проверьте детали перед заказом.</p>
    </section>}
    <button ref={buttonRef} type="button" className="assistant-launcher" aria-label={open ? 'Свернуть ИИ-помощника' : 'Открыть ИИ-помощника'}
      aria-expanded={open} onClick={() => open ? close() : setOpen(true)}>
      {open ? <X size={24} /> : <MessageCircleMore size={26} />}
      {!open && <span>Спросить ИИ</span>}
    </button>
  </div>;
}

