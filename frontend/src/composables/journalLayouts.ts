/**
 * Journal-specific CSS layouts for paper preview.
 * Each journal config defines the visual styling that matches its DOCX template.
 * Used by PreviewTab to render paper content with journal-specific formatting.
 */
export interface JournalLayout {
  /** Human-readable name */
  label: string
  /** Paper container CSS */
  paper: {
    fontFamily: string
    fontSize: string
    lineHeight: string
    columns: string
    columnGap: string
    textAlign: string
    padding: string
    maxWidth: string
    color: string
    background: string
  }
  /** Title styling */
  title: {
    fontSize: string
    fontWeight: string
    textAlign: string
    color: string
    marginBottom: string
  }
  /** Author styling */
  authors: {
    fontSize: string
    textAlign: string
    marginBottom: string
  }
  /** Abstract styling */
  abstract: {
    fontSize: string
    fontWeight: string
    label: string
    labelStyle: string
  }
  /** Section heading */
  heading1: {
    fontSize: string
    fontWeight: string
    color: string
    marginTop: string
    textTransform: string
    numbering: string // 'decimal' | 'roman' | 'none'
  }
  /** Subsection heading */
  heading2: {
    fontSize: string
    fontWeight: string
    fontStyle: string
    marginTop: string
  }
  /** Body text */
  body: {
    fontSize: string
    textAlign: string
    textIndent: string
  }
  /** Header bar (journal name, ISSN) */
  header?: {
    show: boolean
    text: string
    fontSize: string
    color: string
    background: string
    borderBottom: string
  }
  /** Footer (page numbers) */
  footer?: {
    show: boolean
    text: string
    fontSize: string
    color: string
    borderTop: string
  }
  /** Keywords section */
  keywords?: {
    show: boolean
    label: string
    separator: string
  }
  /** References section */
  references: {
    fontSize: string
    label: string
    style: 'numbered' | 'apa'
    hangingIndent: string
  }
}

const baseAcademic: JournalLayout = {
  label: 'Default',
  paper: {
    fontFamily: "'Times New Roman', 'Libertinus Serif', Georgia, serif",
    fontSize: '10pt',
    lineHeight: '1.5',
    columns: '1',
    columnGap: '0',
    textAlign: 'justify',
    padding: '0.75in',
    maxWidth: '8.5in',
    color: '#000',
    background: '#fff',
  },
  title: {
    fontSize: '18pt',
    fontWeight: '700',
    textAlign: 'center',
    color: '#000',
    marginBottom: '12pt',
  },
  authors: {
    fontSize: '10pt',
    textAlign: 'center',
    marginBottom: '6pt',
  },
  abstract: {
    fontSize: '9pt',
    fontWeight: '700',
    label: 'Abstract',
    labelStyle: 'bold',
  },
  heading1: {
    fontSize: '11pt',
    fontWeight: '700',
    color: '#000',
    marginTop: '12pt',
    textTransform: 'none',
    numbering: 'decimal',
  },
  heading2: {
    fontSize: '10pt',
    fontWeight: '600',
    fontStyle: 'italic',
    marginTop: '8pt',
  },
  body: {
    fontSize: '10pt',
    textAlign: 'justify',
    textIndent: '0',
  },
  references: {
    fontSize: '9pt',
    label: 'References',
    style: 'numbered',
    hangingIndent: '0.25in',
  },
}

// ─── Journal Layouts ────────────────────────────────────────────────────────

export const JOURNAL_LAYOUTS: Record<string, JournalLayout> = {
  // IEEE — 2-column, blue header, IEEE-styled
  IEEE: {
    label: 'IEEE',
    paper: {
      ...baseAcademic.paper,
      columns: '2',
      columnGap: '0.25in',
      fontSize: '9pt',
      padding: '0.7in 0.6in',
    },
    title: {
      ...baseAcademic.title,
      fontSize: '22pt',
    },
    authors: {
      ...baseAcademic.authors,
      fontSize: '9pt',
    },
    abstract: {
      ...baseAcademic.abstract,
      fontSize: '9pt',
      fontWeight: '700',
      label: 'Abstract—',
      labelStyle: 'bold italic',
    },
    heading1: {
      ...baseAcademic.heading1,
      fontSize: '10pt',
      textTransform: 'uppercase',
      numbering: 'roman',
    },
    heading2: {
      ...baseAcademic.heading2,
      fontSize: '9pt',
      fontStyle: 'italic',
    },
    body: {
      ...baseAcademic.body,
      fontSize: '9pt',
      textIndent: '0.15in',
    },
    header: {
      show: true,
      text: '> REPLACE THIS LINE WITH YOUR MANUSCRIPT ID NUMBER (DOUBLE-CLICK HERE TO EDIT) <',
      fontSize: '8pt',
      color: '#666',
      background: '#fff',
      borderBottom: '1px solid #999',
    },
    footer: {
      show: true,
      text: '',
      fontSize: '8pt',
      color: '#666',
      borderTop: '1px solid #999',
    },
    keywords: {
      show: true,
      label: 'Keywords—',
      separator: ', ',
    },
    references: {
      ...baseAcademic.references,
      fontSize: '8pt',
      style: 'numbered',
      hangingIndent: '0.2in',
    },
  },

  // ACM — 2-column, ACM-style header
  ACM: {
    label: 'ACM',
    paper: {
      ...baseAcademic.paper,
      columns: '2',
      columnGap: '0.25in',
      fontSize: '9pt',
      padding: '0.75in 0.75in',
    },
    title: {
      ...baseAcademic.title,
      fontSize: '18pt',
      textAlign: 'left',
    },
    authors: {
      ...baseAcademic.authors,
      fontSize: '9pt',
      textAlign: 'left',
    },
    abstract: {
      ...baseAcademic.abstract,
      fontSize: '9pt',
      label: 'Abstract',
      labelStyle: 'bold',
    },
    heading1: {
      ...baseAcademic.heading1,
      fontSize: '11pt',
      textTransform: 'none',
      numbering: 'decimal',
    },
    heading2: {
      ...baseAcademic.heading2,
      fontSize: '10pt',
      fontWeight: '700',
      fontStyle: 'normal',
    },
    body: {
      ...baseAcademic.body,
      fontSize: '9pt',
    },
    header: {
      show: true,
      text: 'ACM Conference Proceedings',
      fontSize: '8pt',
      color: '#000',
      background: '#fff',
      borderBottom: 'none',
    },
    footer: {
      show: true,
      text: '',
      fontSize: '8pt',
      color: '#000',
      borderTop: 'none',
    },
    references: {
      ...baseAcademic.references,
      fontSize: '8pt',
      style: 'numbered',
      hangingIndent: '0.2in',
    },
  },

  // APA — 1-column, running head
  APA: {
    label: 'APA',
    paper: {
      ...baseAcademic.paper,
      columns: '1',
      fontSize: '12pt',
      lineHeight: '2',
      padding: '1in',
    },
    title: {
      ...baseAcademic.title,
      fontSize: '12pt',
      fontWeight: '700',
      textAlign: 'center',
    },
    authors: {
      ...baseAcademic.authors,
      fontSize: '12pt',
    },
    abstract: {
      ...baseAcademic.abstract,
      fontSize: '12pt',
      label: 'Abstract',
      labelStyle: 'bold center',
    },
    heading1: {
      ...baseAcademic.heading1,
      fontSize: '12pt',
      fontWeight: '700',
      textTransform: 'none',
      numbering: 'none',
    },
    heading2: {
      ...baseAcademic.heading2,
      fontSize: '12pt',
      fontWeight: '700',
      fontStyle: 'normal',
    },
    body: {
      ...baseAcademic.body,
      fontSize: '12pt',
      textIndent: '0.5in',
    },
    header: {
      show: true,
      text: 'RUNNING HEAD',
      fontSize: '12pt',
      color: '#000',
      background: '#fff',
      borderBottom: 'none',
    },
    keywords: {
      show: true,
      label: 'Keywords: ',
      separator: ', ',
    },
    references: {
      ...baseAcademic.references,
      fontSize: '12pt',
      style: 'apa',
      hangingIndent: '0.5in',
    },
  },

  // Elsevier — 1-column, numbered sections
  'ELSEVIER': {
    label: 'Elsevier',
    paper: {
      ...baseAcademic.paper,
      columns: '1',
      fontSize: '10pt',
      lineHeight: '1.5',
      padding: '1in',
    },
    title: {
      ...baseAcademic.title,
      fontSize: '14pt',
      textAlign: 'left',
    },
    authors: {
      ...baseAcademic.authors,
      fontSize: '10pt',
      textAlign: 'left',
    },
    abstract: {
      ...baseAcademic.abstract,
      fontSize: '10pt',
      label: 'Abstract',
      labelStyle: 'bold',
    },
    heading1: {
      ...baseAcademic.heading1,
      fontSize: '11pt',
      fontWeight: '700',
      numbering: 'decimal',
      textTransform: 'none',
    },
    heading2: {
      ...baseAcademic.heading2,
      fontSize: '10pt',
      fontWeight: '700',
      fontStyle: 'normal',
    },
    body: {
      ...baseAcademic.body,
      fontSize: '10pt',
    },
    references: {
      ...baseAcademic.references,
      fontSize: '9pt',
      style: 'numbered',
      hangingIndent: '0.25in',
    },
  },

  // JOKI — 1-column, Indonesian journal style
  JOKI: {
    label: 'JOKI',
    paper: {
      ...baseAcademic.paper,
      columns: '1',
      fontSize: '10pt',
      lineHeight: '1.5',
      padding: '1in',
    },
    title: {
      ...baseAcademic.title,
      fontSize: '14pt',
      textAlign: 'center',
    },
    authors: {
      ...baseAcademic.authors,
      fontSize: '10pt',
    },
    abstract: {
      ...baseAcademic.abstract,
      fontSize: '10pt',
      label: 'Abstrak',
      labelStyle: 'bold',
    },
    heading1: {
      ...baseAcademic.heading1,
      fontSize: '11pt',
      fontWeight: '700',
      numbering: 'decimal',
    },
    heading2: {
      ...baseAcademic.heading2,
      fontSize: '10pt',
      fontWeight: '600',
      fontStyle: 'normal',
    },
    body: {
      ...baseAcademic.body,
      fontSize: '10pt',
    },
    keywords: {
      show: true,
      label: 'Kata kunci: ',
      separator: ', ',
    },
    references: {
      ...baseAcademic.references,
      fontSize: '9pt',
      style: 'numbered',
      hangingIndent: '0.25in',
    },
  },
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const JOURNAL_ALIASES: Record<string, string> = {
  'ieee': 'IEEE',
  'acm': 'ACM',
  'apa': 'APA',
  'elsevier': 'ELSEVIER',
  'joki': 'JOKI',
  'jnteti': 'IEEE',
  'jtee': 'IEEE',
  'jti': 'IEEE',
  'jcef': 'IEEE',
  'icet': 'IEEE',
  'uitm': 'IEEE',
  'kkck': 'IEEE',
  'jtransient': 'IEEE',
  'ijb': 'IEEE',
  'iconie': 'IEEE',
  'icoset': 'IEEE',
  'icimece': 'IEEE',
  'elktries': 'IEEE',
  'elkolind': 'IEEE',
  'cerimre': 'IEEE',
  'easr': 'IEEE',
  'djlit': 'IEEE',
  'ccj': 'IEEE',
  'amori': 'IEEE',
  'aej': 'IEEE',
  'jtundip': 'IEEE',
  'energiupm': 'IEEE',
}

/**
 * Resolve journal code to layout.
 * Falls back to IEEE for unrecognized codes.
 */
export function getJournalLayout(code: string | undefined): JournalLayout {
  if (!code) return baseAcademic
  const upper = code.toUpperCase()
  const resolved = JOURNAL_ALIASES[upper] || upper
  return JOURNAL_LAYOUTS[resolved] || baseAcademic
}

/**
 * Get all available journal layout labels for the UI.
 */
export function getJournalLayoutLabels(): string[] {
  return Object.values(JOURNAL_LAYOUTS).map(l => l.label)
}