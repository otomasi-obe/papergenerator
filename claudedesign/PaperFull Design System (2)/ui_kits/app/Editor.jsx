// PaperFull app — Paper Editor. From frontend/src/views/PaperEditorPage.vue
const { useState: useEdState } = React;

const TABS = [
  { id: 'editor', label: '📝 Editor' },
  { id: 'tools', label: '🛠 Tools' },
  { id: 'journal', label: '📚 Journal' },
  { id: 'literature', label: '📖 Literatur' },
  { id: 'files', label: '📂 Files' },
  { id: 'data', label: '📊 Data' },
  { id: 'preview', label: '👁 Preview' },
];

function EditorCard({ accent, children }) {
  return <div className={'ecard' + (accent ? ' accent-' + accent : '')}>{children}</div>;
}

function EditorPane({ paper, pending }) {
  return (
    <div className="pane-inner">
      <EditorCard accent="navy">
        <div className="elabel">Title</div>
        <input className="einput" defaultValue={paper.title} placeholder="Paper title…" />
      </EditorCard>

      <EditorCard accent="navy">
        <div className="elabel">Authors <button className="btn-add">＋ Author</button></div>
        {paper.authors.map((a, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
            <span className="drag">⠿</span>
            <input className="einput" defaultValue={a.name} placeholder="Name" />
            <input className="einput" defaultValue={a.affil} placeholder="Affiliation" />
          </div>
        ))}
      </EditorCard>

      <EditorCard accent="navy">
        <div className="elabel">Abstract</div>
        <textarea className="einput" rows="3" style={{ resize: 'none' }} defaultValue={paper.abstract}></textarea>
      </EditorCard>

      <EditorCard accent="cream">
        <div className="elabel">Keywords</div>
        <div className="kw-row">
          {paper.keywords.map((k, i) => <span className="kw" key={i}>{k} <b>✕</b></span>)}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input className="einput" placeholder="Add keyword…" />
          <button className="btn-add">Add</button>
        </div>
      </EditorCard>

      {paper.sections.map((s, i) => (
        <EditorCard accent="cream" key={i}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span className="drag">⠿</span>
            <span className="sec-tag">Section {toRoman(i + 1)}</span>
            <input className="einput" defaultValue={s.title} style={{ fontWeight: 600 }} />
          </div>
          <p style={{ fontSize: 13, color: 'var(--fg-base)', lineHeight: 1.6, margin: 0 }}>{s.body}</p>
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            <button className="btn-add">＋ Text</button>
            <button className="btn-add">＋ Image</button>
            <button className="btn-add">＋ Table</button>
            <button className="btn-add">＋ Formula</button>
          </div>
        </EditorCard>
      ))}

      <button className="add-section">＋ Add Section</button>

      <div style={{ height: 12 }}></div>
      <EditorCard accent="red">
        <div className="elabel">References <button className="btn-add">＋ Reference</button></div>
        {paper.references.map((r, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: 'var(--fg-muted)', width: 22, textAlign: 'right' }}>[{i + 1}]</span>
            <input className="einput" defaultValue={r} style={{ fontSize: 12 }} />
          </div>
        ))}
      </EditorCard>
    </div>
  );
}

function PreviewPane({ paper }) {
  return (
    <div className="pane-inner" style={{ background: 'var(--bg-app)' }}>
      <div className="paper-preview">
        <h1>{paper.title}</h1>
        <div className="authors">
          {paper.authors.map((a) => a.name).join(', ')}<br />
          <em>{paper.authors[0].affil}</em>
        </div>
        <div className="abstract"><b><i>Abstract—</i></b><i>{paper.abstract}</i></div>
        <div className="cols2" style={{ marginTop: 16 }}>
          {paper.sections.map((s, i) => (
            <React.Fragment key={i}>
              <div className="sech">{toRoman(i + 1)}. {s.title.toUpperCase()}</div>
              <p>{s.body}</p>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

function PlaceholderPane({ label }) {
  return (
    <div className="pane-inner">
      <EditorCard>
        <div className="elabel">{label}</div>
        <p style={{ fontSize: 13, color: 'var(--fg-muted)', margin: 0, lineHeight: 1.6 }}>
          This tab exists in the product but isn’t recreated in the UI kit — it’s left intentionally blank.
          See the <b>Editor</b> and <b>Preview</b> tabs for the high-fidelity surfaces.
        </p>
      </EditorCard>
    </div>
  );
}

function Editor({ paper, onBack, messages, onSend, streaming }) {
  const [tab, setTab] = useEdState('editor');
  const [chatOpen, setChatOpen] = useEdState(true);
  const [journal, setJournal] = useEdState('IEEE');
  const pending = 3;

  function renderPane() {
    const T = window.PFTabs || {};
    if (tab === 'editor') return <EditorPane paper={paper} pending={pending} />;
    if (tab === 'preview') return <PreviewPane paper={paper} />;
    if (tab === 'tools') return <window.PFTools />;
    if (tab === 'journal') return <T.JournalTab selected={journal} onSelect={setJournal} />;
    if (tab === 'literature') return <T.LiteratureTab />;
    if (tab === 'files') return <T.FilesTab />;
    if (tab === 'data') return <T.DataTab />;
    const lbl = TABS.find((t) => t.id === tab).label;
    return <PlaceholderPane label={lbl} />;
  }

  return (
    <div className="editor-shell">
      <div className="toolbar">
        <div className="toolbar-row">
          <button className="tb-back" onClick={onBack}>← Papers</button>
          <span className="tb-div">|</span>
          <input className="tb-title" defaultValue={paper.title} />
          <span className="tb-saved">Saved · just now</span>
          <div className="tb-group">
            <button className="tb">📄 DOCX</button>
            <button className="tb">↶ Undo</button>
            <button className="tb">↷ Redo</button>
            {TABS.map((t) => (
              <button key={t.id}
                className={'tb' + (tab === t.id ? ' active' : '') + (t.id === 'preview' && pending ? ' pending-badge' : '')}
                data-pending={t.id === 'preview' ? pending : null}
                onClick={() => setTab(tab === t.id ? '' : t.id)}>{t.label}</button>
            ))}
            <button className={'tb' + (chatOpen ? ' active' : '')} onClick={() => setChatOpen(!chatOpen)}>💬 AI Chat</button>
          </div>
        </div>
      </div>

      <div className="split">
        {tab && <div className={'pane' + (chatOpen ? '' : ' pane-full')}>{renderPane()}</div>}
        {chatOpen && <Chat messages={messages} onSend={onSend} streaming={streaming} full={!tab} />}
      </div>
    </div>
  );
}

window.Editor = Editor;
