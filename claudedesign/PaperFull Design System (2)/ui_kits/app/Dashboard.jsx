// PaperFull app — Dashboard ("My Papers"). From frontend/src/views/DashboardPage.vue
function Dashboard({ papers, onOpen, onNew, onCopy, onDelete }) {
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>My Papers</h1>
          <p className="sub">{papers.length} paper{papers.length === 1 ? '' : 's'}</p>
        </div>
        <button className="btn-primary" onClick={onNew}>＋ New Paper</button>
      </div>

      {papers.length === 0 ? (
        <div className="empty">
          <div className="e" aria-hidden="true">📄</div>
          <h2>No papers yet</h2>
          <p>Create your first paper with AI assistance</p>
          <button className="btn-primary" onClick={onNew}>Create First Paper</button>
        </div>
      ) : (
        <div className="papers-grid">
          {papers.map((p) => (
            <article className="paper" key={p.id}>
              <div className="pb" onClick={() => onOpen(p.id)}>
                <h3>{p.title || 'Untitled Paper'}</h3>
                <div className="chips">
                  <span className="chip">Updated {p.updated}</span>
                  <span className="chip">🖼️ {p.images} image{p.images === 1 ? '' : 's'}</span>
                  {p.journal && <span className="chip">{p.journal}</span>}
                  {p.sections ? <span className="chip">{p.sections} sections</span> : null}
                </div>
              </div>
              <div className="paper-acts">
                <button className="pa open" onClick={() => onOpen(p.id)}>Open</button>
                <button className="pa copy" onClick={() => onCopy(p.id)}>Copy</button>
                <button className="pa del" onClick={() => onDelete(p.id)}>Delete</button>
              </div>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}

window.Dashboard = Dashboard;
