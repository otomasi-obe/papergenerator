import { create } from 'zustand';

export const useChatStore = create((set, get) => ({
  conversations: [],
  currentConversationId: null,
  messages: [],
  isTyping: false,

  setMessages: (messages) => set({ messages }),
  addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),
  setTyping: (isTyping) => set({ isTyping })
}));
