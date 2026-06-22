import { create } from 'zustand';

export const useUiStore = create((set, get) => ({
  tabs: {},         // { paperId: 'editor' | 'preview' }
  editorVisible: {}, // { paperId: boolean }
  rightPanels: {},  // { paperId: '' | 'chat' | 'journal' | 'literature' | 'files' | 'data' | 'image' | 'tool-workspace' }
  toolsOpen: {},    // { paperId: boolean }

  getTab: (paperId) => get().tabs[paperId] || 'editor',
  setTab: (paperId, tab) => set((state) => ({ tabs: { ...state.tabs, [paperId]: tab } })),

  getEditorVisible: (paperId) => get().editorVisible[paperId] ?? true,
  setEditorVisible: (paperId, visible) => set((state) => ({ editorVisible: { ...state.editorVisible, [paperId]: visible } })),

  getRightPanel: (paperId) => get().rightPanels[paperId] || 'chat',
  setRightPanel: (paperId, panel) => set((state) => ({ rightPanels: { ...state.rightPanels, [paperId]: panel } })),

  getToolsOpen: (paperId) => get().toolsOpen[paperId] || false,
  setToolsOpen: (paperId, open) => set((state) => ({ toolsOpen: { ...state.toolsOpen, [paperId]: open } })),
}));
