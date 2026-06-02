// PaperFull — Landing page (marketing). Recreated from frontend/src/views/LandingPage.vue
const { useState } = React;

const FEATURES = [
  { icon: '⚡', title: 'AI Paper Generation', description: 'Complete papers with 4000+ words from a single prompt. AI writes every section with academic style, proper citations, and anti-AI-detection strategies.' },
  { icon: '🌍', title: 'Multi-Journal Support', description: 'IEEE, international journals, SINTA-indexed journals, and conferences. Auto-adapts formatting to each venue\u2019s requirements.' },
  { icon: '🧮', title: 'LaTeX Formula Generation', description: 'DOCX-compatible LaTeX for control theory, kinematics, machine learning, and power electronics.' },
  { icon: '🖼️', title: 'AI Figure Generation', description: 'Block diagrams, circuit schematics, charts, heatmaps, and experimental-setup illustrations from prompts.' },
  { icon: '📊', title: 'Table & Reference Management', description: 'Formatted tables with realistic data and 20+ references (IEEE, APA, Vancouver), internally consistent.' },
  { icon: '🎯', title: 'Multi-Domain Support', description: 'Robotics, mechatronics, AI/ML, PLC automation, power electronics, embedded systems, and IoT.' },
];

const PUB_TYPES = [
  { icon: '📚', title: 'IEEE Journals', body: 'TIE, TPEL, RA-L, TMECH, IoT-J, Access and more. IEEE citation format and conference standards.' },
  { icon: '🌐', title: 'International Journals', body: 'Scopus & Web of Science indexed. APA, Vancouver and custom citation formats supported.' },
  { icon: '🏆', title: 'SINTA Journals', body: 'Indonesian SINTA 1\u20136 indexed journals. Formatting for national publication requirements.' },
  { icon: '🎤', title: 'Conferences', body: 'International and local conferences. ICRA, IROS, IECON and other technical venues.' },
];

function Landing({ onSignIn }) {
  return (
    <div className="mk">
      <nav className="nav">
        <div className="nav-brand">
          <img src="../../assets/logo-with-text.png" alt="PaperFull" />
          <span className="tag-pill">Multi-Journal</span>
        </div>
        <button className="btn-signin" onClick={onSignIn}>Sign In</button>
      </nav>

      <section className="hero">
        <div>
          <div className="eyebrow"><span className="dot"></span>AI-Powered Academic Paper Writing</div>
          <h1>Generate Papers for <span className="grad">Journal</span> or Conference</h1>
          <p>Generate publication-ready papers for IEEE, international journals, SINTA-indexed journals, and conferences. Auto-format with LaTeX formulas, figures, tables, and references — export to DOCX ready for submission.</p>
          <div className="hero-cta">
            <button className="btn-lg btn-fill" onClick={onSignIn}>Get Started</button>
            <a className="btn-lg btn-outline" href="#features">Learn More →</a>
          </div>
        </div>
        <div className="hero-img-wrap">
          <div className="glow"></div>
          <img className="hero-img" src="../../assets/landing-page.jpg" alt="PaperFull editor preview" />
        </div>
      </section>

      <section className="trust">
        <img src="../../assets/trust-strip-bg.jpg" alt="" aria-hidden="true" />
        <div className="scrim"></div>
        <div className="trust-inner">
          <p className="trust-label">Trusted across disciplines · IEEE · SINTA · International Journals · Conferences</p>
          <div className="stats">
            <div className="stat"><div className="n">100+</div><div className="l">Domain topics</div></div>
            <div className="stat"><div className="n">20+</div><div className="l">Citation styles</div></div>
            <div className="stat"><div className="n">4000+</div><div className="l">Words per paper</div></div>
            <div className="stat"><div className="n">DOCX</div><div className="l">Submission-ready</div></div>
          </div>
        </div>
      </section>

      <section className="section" id="features">
        <div className="feat-intro">
          <div>
            <h2>Everything you need to write great papers</h2>
            <p className="lede">From the first draft to the final DOCX, PaperFull handles the structural work so you can focus on the ideas. Domain-aware prompts, anti-detection writing, full citation hygiene, and a chat assistant that reads your reference PDFs.</p>
          </div>
          <img src="../../assets/feature-illustration.jpg" alt="PaperFull feature illustration" />
        </div>
        <div className="cards">
          {FEATURES.map((f) => (
            <div className="fcard" key={f.title}>
              <div className="ic" aria-hidden="true">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.description}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section center">
        <h2>Supported Publication Types</h2>
        <p className="lede">Generate papers for various publication venues with proper formatting and citation styles.</p>
        <div className="grid4">
          {PUB_TYPES.map((p) => (
            <div className="pcard" key={p.title}>
              <div className="ic" aria-hidden="true">{p.icon}</div>
              <h3>{p.title}</h3>
              <p>{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="cta-wrap">
        <div className="cta-box">
          <h2>Ready to write your paper?</h2>
          <p>Join researchers using AI to accelerate their academic writing.</p>
          <button className="btn-lg" onClick={onSignIn}>Start Writing for Free</button>
        </div>
      </div>

      <footer className="footer">© 2026 PaperFull · Multi-Journal Academic Paper AI Tool</footer>
    </div>
  );
}

window.Landing = Landing;
