// PaperFull app — AI chat panel. From frontend/src/components/chat/* + ChatInput.vue
const { useState: useChatState, useRef: useChatRef, useEffect: useChatEffect } = React;

const SUGGESTIONS = [
  { key: 'outline', label: 'Buat outline', text: 'Generate a section outline' },
  { key: 'abstract', label: 'Tulis abstract', text: 'Write the abstract' },
  { key: 'refs', label: 'Tambah referensi', text: 'Add 5 IEEE references' },
  { key: 'figure', label: 'Generate figure', text: 'Create a block diagram' },
];

function Chat({ messages, onSend, streaming, full }) {
  const [text, setText] = useChatState('');
  const scrollRef = useChatRef(null);

  useChatEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, streaming]);

  function submit() {
    if (!text.trim() || streaming) return;
    onSend(text.trim());
    setText('');
  }

  return (
    <div className={'chat-panel' + (full ? ' full' : '')}>
      <div className="chat-head">💬 AI Chat</div>
      <div className="chat-scroll" ref={scrollRef}>
        {messages.map((m, i) => (
          <div key={i} className={'bubble ' + m.role}>
            {m.text}
            {m.tool && <div className="tool">🔧 {m.tool}</div>}
          </div>
        ))}
        {streaming && (
          <div className="bubble ai"><span className="typing"><i></i><i></i><i></i></span></div>
        )}
      </div>
      {!text && (
        <div className="chips-row">
          {SUGGESTIONS.map((s) => (
            <button key={s.key} className="sugg" disabled={streaming} onClick={() => onSend(s.text)}>{s.label}</button>
          ))}
        </div>
      )}
      <div className="composer-wrap">
        <div className="composer">
          <button className="cbtn" title="Saran">💡</button>
          <button className="cbtn" title="Lampirkan">＋</button>
          <textarea
            rows="1"
            value={text}
            placeholder={streaming ? 'AI mengetik…' : 'Ketik pesan…'}
            disabled={streaming}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
          ></textarea>
          <button className="send" onClick={submit} disabled={!text.trim() || streaming}>{Icon.send({})}</button>
        </div>
      </div>
    </div>
  );
}

window.Chat = Chat;
window.SUGGESTIONS = SUGGESTIONS;
