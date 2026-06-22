import { create } from 'zustand';

// Dummy initial paper data
const initialPaper = {
  id: 'paper-123',
  title: 'Analyzing AI Usability in Advanced Interfaces',
  abstract: 'This paper explores the usability of advanced agentic AI interfaces...',
  keywords: ['AI', 'Usability', 'Interface Design'],
  authors: [
    { name: 'Dr. Jane Doe', email: 'jane@university.edu', affiliation: 'University of Technology', location: 'New York, USA' }
  ],
  sections: [
    {
      id: 'sec-1',
      title: 'INTRODUCTION',
      content: [{ type: 'text', content: 'Artificial Intelligence has rapidly evolved...' }],
      subsections: []
    },
    {
      id: 'sec-2',
      title: 'METHODOLOGY',
      content: [{ type: 'text', content: 'We conducted a study with 50 participants...' }],
      subsections: [
        {
          id: 'sub-2-1',
          title: 'Participants',
          content: [{ type: 'text', content: 'Participants were selected from...' }]
        }
      ]
    }
  ],
  references: ['Smith, J. (2025). AI and Usability. Journal of AI, 1(1), 1-10.']
};

export const usePaperStore = create((set, get) => ({
  paper: initialPaper,
  currentPaperId: initialPaper.id,
  loading: false,
  pendingCount: 0,
  canUndo: false,
  canRedo: false,
  toast: { show: false, message: '', type: 'info' },

  setPaper: (paper) => set({ paper }),
  setPaperTitle: (title) => set((state) => ({ paper: { ...state.paper, title } })),
  setPaperAbstract: (abstract) => set((state) => ({ paper: { ...state.paper, abstract } })),
  
  addAuthor: () => set((state) => ({
    paper: {
      ...state.paper,
      authors: [...state.paper.authors, { name: '', email: '', affiliation: '', location: '' }]
    }
  })),
  removeAuthor: (index) => set((state) => ({
    paper: {
      ...state.paper,
      authors: state.paper.authors.filter((_, i) => i !== index)
    }
  })),
  
  addKeyword: (keyword) => set((state) => ({
    paper: { ...state.paper, keywords: [...state.paper.keywords, keyword] }
  })),
  removeKeyword: (index) => set((state) => ({
    paper: { ...state.paper, keywords: state.paper.keywords.filter((_, i) => i !== index) }
  })),
  
  addSection: () => set((state) => ({
    paper: {
      ...state.paper,
      sections: [...state.paper.sections, { id: `sec-${Date.now()}`, title: '', content: [], subsections: [] }]
    }
  })),
  removeSection: (index) => set((state) => ({
    paper: {
      ...state.paper,
      sections: state.paper.sections.filter((_, i) => i !== index)
    }
  })),

  showToast: (message, type = 'info') => {
    set({ toast: { show: true, message, type } });
    setTimeout(() => set({ toast: { show: false, message: '', type: 'info' } }), 3000);
  },

  undo: () => { /* mock */ },
  redo: () => { /* mock */ },
  exportDocx: () => { /* mock */ }
}));
