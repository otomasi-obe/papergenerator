// PaperFull app — AI writing tools suite (Tools tab).
// Designed in-brand at the user's request (extends the product; "anti-AI detection" is a stated feature).
const { useState: useToolState } = React;

const SAMPLE = 'This paper presents an adaptive sliding-mode controller for the stabilization of a two-wheeled self-balancing robot. The proposed method utilizes a Lyapunov-based adaptation law to tune the switching gain online, thereby reducing chattering while preserving robustness against external disturbance.';

const TOOLS = [
  { id: 'paraphrase', icon: '✍️', tint: 'var(--navy-500)', title: 'Paraphrase', desc: 'Rewrite passages in a different tone or strength while keeping the meaning.' },
  { id: 'translate', icon: '🌐', tint: 'var(--academic-conference)', title: 'Translator', desc: 'Translate between Indonesian, English and 20+ languages — academic register.' },
  { id: 'humanizer', icon: '🧬', tint: 'var(--accent-success)', title: 'Humanizer', desc: 'Rework AI-sounding prose to read naturally and pass AI detectors.' },
  { id: 'detector', icon: '🔍', tint: 'var(--gold-500)', title: 'AI Detector', desc: 'Estimate how likely a passage reads as AI-generated.' },
  { id: 'plagiarism', icon: '📋', tint: 'var(--accent-danger)', title: 'Plagiarism Check', desc: 'Scan against published sources and report a similarity score.' },
  { id: 'grammar', icon: '✓', tint: 'var(--teal-accent)', title: 'Grammar & Style', desc: 'Fix grammar, clarity and academic style issues inline.' },
  { id: 'summarize', icon: '📝', tint: 'var(--navy-700)', title: 'Summarize', desc: 'Condense a section or reference into a TL;DR or abstract.' },
  { id: 'citation', icon: '📑', tint: 'var(--gold-600)', title: 'Citation Generator', desc: 'Turn a DOI, URL or title into a formatted reference.' },
];

function Gauge({ pct, color, title, desc }) {
  return (
    <div className="gauge">
      <div className="ring" style={{ background: `conic-gradient(${color} ${pct * 3.6}deg, var(--border-soft) 0deg)` }}>
        <div style={{ width: 46, height: 46, borderRadius: '50%', background: 'var(--bg-elevated)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--fg-strong)' }}>{pct}%</div>
      </div>
      <div className="gx"><div className="gt">{title}</div><div className="gd">{desc}</div></div>
    </div>
  );
}

function ToolWorkspace({ tool, onBack }) {
  const [input, setInput] = useToolState(SAMPLE);
  const [ran, setRan] = useToolState(false);
  const [busy, setBusy] = useToolState(false);
  const [opt, setOpt] = useToolState(tool.id === 'translate' ? 'Indonesian' : tool.id === 'paraphrase' ? 'Standard' : 'Standard');

  function run() { setBusy(true); setRan(false); setTimeout(() => { setBusy(false); setRan(true); }, 1200); }

  const outputs = {
    paraphrase: <span>We introduce an adaptive sliding-mode control scheme to stabilise a two-wheeled self-balancing robot. A Lyapunov-driven adaptation rule adjusts the switching gain in real time, which suppresses chattering without compromising robustness to outside disturbances.</span>,
    translate: <span>Makalah ini menyajikan pengendali sliding-mode adaptif untuk stabilisasi robot keseimbangan beroda dua. Metode yang diusulkan memanfaatkan hukum adaptasi berbasis Lyapunov untuk menyetel switching gain secara daring, sehingga mengurangi chattering sekaligus menjaga ketahanan terhadap gangguan eksternal.</span>,
    humanizer: <span>We built an adaptive sliding-mode controller to keep a two-wheeled self-balancing robot upright. Rather than fixing the switching gain, a Lyapunov-based rule nudges it on the fly — so the system stays robust to disturbances but doesn't chatter the way a stiff controller would.</span>,
    summarize: <span><strong>TL;DR —</strong> An adaptive sliding-mode controller stabilises a balancing robot by tuning its switching gain online via a Lyapunov law, cutting chattering while staying robust to disturbance.</span>,
    citation: <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>[1] R. Coban, "Adaptive sliding-mode control of a two-wheeled balancing robot," <em>ISA Transactions</em>, vol. 90, pp. 147–159, 2019, doi: 10.1016/j.isatra.2019.01.012.</span>,
    grammar: <span>This paper <span className="hl-del">presents</span> <span className="hl-add">proposes</span> an adaptive sliding-mode controller for <span className="hl-del">the stabilization of</span> <span className="hl-add">stabilising</span> a two-wheeled self-balancing robot. The proposed method <span className="hl-del">utilizes</span> <span className="hl-add">uses</span> a Lyapunov-based adaptation law to tune the switching gain online, <span className="hl-del">thereby reducing</span> <span className="hl-add">reducing</span> chattering while preserving robustness.</span>,
  };

  return (
    <div className="pane-inner">
      <button className="tool-back" onClick={onBack}>← All tools</button>
      <div className="tab-head"><h2><span>{tool.icon}</span> {tool.title}</h2><p>{tool.desc}</p></div>

      {/* controls */}
      <div className="tool-controls">
        {tool.id === 'paraphrase' && (
          <div className="chip-toggle">{['Standard', 'Formal', 'Fluent', 'Concise'].map((o) => <button key={o} className={opt === o ? 'on' : ''} onClick={() => setOpt(o)}>{o}</button>)}</div>
        )}
        {tool.id === 'translate' && (
          <React.Fragment>
            <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>English →</span>
            <select className="select" value={opt} onChange={(e) => setOpt(e.target.value)}>
              <option>Indonesian</option><option>Spanish</option><option>German</option><option>Chinese (Simplified)</option><option>Arabic</option>
            </select>
          </React.Fragment>
        )}
        {tool.id === 'humanizer' && (
          <div className="chip-toggle">{['Light', 'Standard', 'Aggressive'].map((o) => <button key={o} className={opt === o ? 'on' : ''} onClick={() => setOpt(o)}>{o}</button>)}</div>
        )}
        {tool.id === 'summarize' && (
          <div className="chip-toggle">{['TL;DR', 'Abstract', 'Bullets'].map((o) => <button key={o} className={opt === o ? 'on' : ''} onClick={() => setOpt(o)}>{o}</button>)}</div>
        )}
        <button className="btn-primary" onClick={run} disabled={busy}>{busy ? 'Working…' : (tool.id === 'detector' || tool.id === 'plagiarism' ? 'Scan' : 'Run')}</button>
      </div>

      {/* gauges for detector / plagiarism */}
      {ran && tool.id === 'detector' && <Gauge pct={12} color="var(--accent-success)" title="12% likely AI-generated" desc="Reads mostly human · low detector risk after humanizing." />}
      {ran && tool.id === 'plagiarism' && <Gauge pct={4} color="var(--accent-success)" title="4% similarity" desc="No significant overlap with indexed sources. 1 minor match (common phrase)." />}

      <div className="tool-work">
        <div className="tool-io">
          <div className="io-head"><span>Input</span><span style={{ fontWeight: 400, color: 'var(--fg-muted)' }}>{input.trim().split(/\s+/).length} words</span></div>
          <textarea value={input} onChange={(e) => setInput(e.target.value)} />
        </div>
        <div className="tool-io">
          <div className="io-head"><span>{tool.id === 'detector' || tool.id === 'plagiarism' ? 'Report' : 'Output'}</span>{ran && <button className="btn-add">Copy</button>}</div>
          <div className="io-out">
            {busy && <span className="typing"><i></i><i></i><i></i></span>}
            {!busy && !ran && <span style={{ color: 'var(--fg-muted)' }}>Click {tool.id === 'detector' || tool.id === 'plagiarism' ? '"Scan"' : '"Run"'} to process the input on the left.</span>}
            {!busy && ran && (outputs[tool.id] || <span style={{ color: 'var(--fg-muted)' }}>Done — see the report above.</span>)}
          </div>
        </div>
      </div>
    </div>
  );
}

function ToolsTab() {
  const [active, setActive] = useToolState(null);
  if (active) return <ToolWorkspace tool={active} onBack={() => setActive(null)} />;
  return (
    <div className="pane-inner">
      <div className="tab-head">
        <h2>🛠 Tools</h2>
        <p>AI writing toolkit — paraphrase, translate, humanize, and check your draft before submission. Each tool runs on the selected text or your whole paper.</p>
      </div>
      <div className="tools-grid">
        {TOOLS.map((t) => (
          <div className="tool-card" key={t.id} onClick={() => setActive(t)}>
            <div className="tool-ic" style={{ background: t.tint, color: '#fff' }}>{t.icon}</div>
            <h3>{t.title}</h3>
            <p>{t.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

window.PFTools = ToolsTab;
