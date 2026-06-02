// PaperFull app — tab content recreations: Journal · Literatur · Files · Data
// From frontend/src/components/{JournalTab,LiteratureTab,FilesTab,DataTab}.vue
const { useState: useTabState } = React;

const JOURNALS = [
  { name: 'IEEE', desc: 'Two-column · IEEEtran' },
  { name: 'ACM', desc: 'acmart' },
  { name: 'APA 7th', desc: 'Author-date' },
  { name: 'Elsevier', desc: 'elsarticle' },
  { name: 'MDPI', desc: 'Open access' },
  { name: 'Springer', desc: 'LNCS' },
  { name: 'Vancouver', desc: 'Numbered' },
  { name: 'SINTA 2', desc: 'Nasional terakreditasi' },
  { name: 'JNTETI', desc: 'SINTA · UGM' },
  { name: 'JOKI', desc: 'SINTA · informatika' },
];

function JournalTab({ selected, onSelect }) {
  const [open, setOpen] = useTabState(false);
  const [q, setQ] = useTabState('');
  const filtered = JOURNALS.filter((j) => j.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="pane-inner" style={{ maxWidth: 760 }}>
      <div className="tab-head">
        <h2>📚 Journal</h2>
        <p>Pilih jurnal/template tujuan untuk export DOCX. Pilihan ini menentukan template generator yang dipakai saat klik "Export DOCX".</p>
      </div>
      <div className="ecard">
        <label className="field-label">Export format</label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 12, color: 'var(--fg-muted)' }}>Saat ini:</span>
          <span className="journal-pill">{selected}</span>
        </div>
        <div className="combo">
          <input className="einput" placeholder="🔍 Cari jurnal (contoh: IEEE, JNTETI, SINTA…)"
            value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} />
          {open && filtered.length > 0 && (
            <ul className="combo-list">
              {filtered.map((j) => (
                <li key={j.name} className={selected === j.name ? 'on' : ''}
                  onClick={() => { onSelect(j.name); setOpen(false); setQ(''); }}>
                  <span>{j.name} <span style={{ color: 'var(--fg-muted)', fontSize: 11 }}>· {j.desc}</span></span>
                  {selected === j.name && <span style={{ fontSize: 11, color: 'var(--accent-success)' }}>✓ active</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="tpl-grid">
          {JOURNALS.map((j) => (
            <div key={j.name} className={'tpl' + (selected === j.name ? ' active' : '')} onClick={() => onSelect(j.name)}>
              <div className="nm">{j.name}</div>
              <div className="ds">{j.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const LITERATURE = [
  { cite: 'Slotine & Li (1991)', title: 'Applied Nonlinear Control', venue: 'Prentice Hall', type: 'book', rel: 5 },
  { cite: 'Utkin (1977)', title: 'Variable structure systems with sliding modes', venue: 'IEEE TAC', type: 'journal', rel: 5 },
  { cite: 'Coban (2019)', title: 'Adaptive SMC of a balancing robot', venue: 'ISA Transactions', type: 'journal', rel: 4 },
  { cite: 'Kim et al. (2022)', title: 'Chattering-free adaptive SMC for mobile robots', venue: 'arXiv:2203.xxxx', type: 'preprint', rel: 4 },
  { cite: 'Pratama (2023)', title: 'Kendali robot keseimbangan berbasis STM32', venue: 'JNTETI · SINTA 2', type: 'gold', rel: 3 },
];

function LiteratureTab() {
  const [running, setRunning] = useTabState(false);
  const [done, setDone] = useTabState(false);
  function runSLR() { setRunning(true); setTimeout(() => { setRunning(false); setDone(true); }, 1500); }
  return (
    <div className="pane-inner" style={{ maxWidth: 920 }}>
      <div className="tab-head row-between">
        <div>
          <h2>📖 Literatur</h2>
          <p>Tabel referensi paper. Hasil SLR otomatis tersimpan di sini, dan dipakai sebagai sumber utama saat generate paper lengkap.</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-add">📂 Import dari File</button>
          <button className="btn-primary" style={{ padding: '8px 14px' }}>＋ Tambah Manual</button>
        </div>
      </div>
      <div className="well">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <strong style={{ fontSize: 13, color: 'var(--fg-strong)' }}>🔍 Jalankan SLR</strong>
          <span className="src-tags">Multi-source · OpenAlex · Crossref · arXiv · IEEE · SINTA</span>
        </div>
        <div className="slr-row">
          <input className="einput" placeholder="Ketik topik (mis. 'adaptive sliding-mode control balancing robot')" />
          <select className="select"><option>Top 20</option><option>Top 30</option><option>Top 50</option></select>
          <button className="btn-primary" onClick={runSLR} disabled={running}>{running ? 'Mencari…' : 'Jalankan SLR'}</button>
        </div>
        {running && <div style={{ marginTop: 10, fontSize: 12, color: 'var(--fg-muted)' }}>⏳ Querying OpenAlex · Crossref · arXiv…</div>}
        {done && <div style={{ marginTop: 10, fontSize: 12, color: 'var(--accent-success)' }}>✓ 24 referensi ditemukan & disaring ke 5 paling relevan.</div>}
      </div>
      <table className="lit-table">
        <thead><tr><th>Citation</th><th>Title</th><th>Venue</th><th>Type</th><th>Relevance</th></tr></thead>
        <tbody>
          {LITERATURE.map((r, i) => (
            <tr key={i}>
              <td className="cite">{r.cite}</td>
              <td>{r.title}</td>
              <td>{r.venue}</td>
              <td><span className={'tag ' + r.type}>{r.type === 'gold' ? 'SINTA' : r.type}</span></td>
              <td><span className="stars">{'★'.repeat(r.rel)}{'☆'.repeat(5 - r.rel)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const FILES = [
  { icon: '📄', name: 'utkin_1977_vss.pdf', meta: 'PDF · 1.2 MB · 8 pages' },
  { icon: '📄', name: 'coban_2019_asmc.pdf', meta: 'PDF · 2.4 MB · 12 pages' },
  { icon: '📝', name: 'lab_notes_balancing.docx', meta: 'DOCX · 340 KB' },
];

function FilesTab() {
  const [sub, setSub] = useTabState('docs');
  const [sel, setSel] = useTabState(0);
  return (
    <div className="pane-inner" style={{ maxWidth: 980 }}>
      <div className="subtabs">
        <button className={'subtab' + (sub === 'docs' ? ' on' : '')} onClick={() => setSub('docs')}>📄 Dokumen</button>
        <button className={'subtab' + (sub === 'figures' ? ' on' : '')} onClick={() => setSub('figures')}>🖼 Figures &amp; Images</button>
      </div>
      <div className="tab-head row-between">
        <div>
          <h2 style={{ fontFamily: 'var(--font-sans)', fontSize: 17 }}>Files</h2>
          <p>PDF / DOCX / DOC / TXT / MD / XLSX / CSV — max 30MB per file. Bisa upload banyak file sekaligus.</p>
        </div>
        <button className="btn-primary" style={{ padding: '8px 14px' }}>＋ Upload file</button>
      </div>
      {sub === 'docs' ? (
        <div className="files-layout">
          <div className="filelist">
            <div className="fl-head">{FILES.length} files</div>
            {FILES.map((f, i) => (
              <div key={i} className={'fl-item' + (sel === i ? ' on' : '')} onClick={() => setSel(i)}>
                <span className="fl-icon">{f.icon}</span>
                <div><div className="fl-name">{f.name}</div><div className="fl-meta">{f.meta}</div></div>
              </div>
            ))}
          </div>
          <div className="doc-preview">
            <div className="dp-title">{FILES[sel].name}</div>
            <div className="fl-meta">{FILES[sel].meta} · diekstrak untuk konteks chat &amp; SLR</div>
            <div className="dp-extract">
              <strong>Extracted text (preview):</strong><br />
              "The variable structure control approach guarantees finite-time convergence to the sliding manifold despite bounded matched uncertainty. The switching gain must exceed the disturbance bound to maintain the reaching condition…"
            </div>
          </div>
        </div>
      ) : (
        <div className="dropzone">🖼 Klik atau seret gambar ke sini.<br /><span style={{ fontSize: 12 }}>Figures yang di-generate AI juga muncul di sini.</span></div>
      )}
    </div>
  );
}

function DataTab() {
  const data = [
    { m: 'Fixed-gain SMC', settle: 2.4, oss: 6.1 },
    { m: 'Adaptive SMC', settle: 1.5, oss: 4.8 },
    { m: 'LQR baseline', settle: 3.1, oss: 8.0 },
  ];
  const max = 3.1;
  return (
    <div className="pane-inner" style={{ maxWidth: 880 }}>
      <div className="tab-head row-between">
        <div>
          <h2>📊 Data</h2>
          <p>Mulai dari sumber data — unggah file (PDF / Excel / CSV / Word) atau tempel manual. Satu sumber bisa menghasilkan beberapa tabel, dan tiap tabel beberapa grafik.</p>
        </div>
        <button className="btn-primary" style={{ padding: '8px 14px' }}>＋ Tambah sumber data</button>
      </div>
      <div className="ecard">
        <div className="field-label">Table 1 — Controller performance comparison</div>
        <table className="dtable">
          <thead><tr><th>Method</th><th>Settling time (s)</th><th>Overshoot (°)</th></tr></thead>
          <tbody>{data.map((d, i) => <tr key={i}><td>{d.m}</td><td>{d.settle}</td><td>{d.oss}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="ecard">
        <div className="field-label">Fig. 1 — Settling time by method (bar chart)</div>
        <div className="barchart">
          {data.map((d, i) => (
            <div className="bar-col" key={i}>
              <div className={'bar' + (i === 1 ? ' alt' : '')} style={{ height: (d.settle / max * 100) + '%' }}></div>
              <div className="bar-lbl">{d.m.split(' ')[0]}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

window.PFTabs = { JournalTab, LiteratureTab, FilesTab, DataTab };
