/**
 * Toast Composable - Notification system for user feedback
 * Addresses UX issues around feedback clarity
 * 
 * Usage:
 * const toast = useToast()
 * toast.success('Paper saved successfully!')
 * toast.error('Failed to save paper')
 */

import { ref } from 'vue'

export interface ToastMessage {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  message: string
  duration?: number
}

const toasts = ref<ToastMessage[]>([])
let toastId = 0

function addToast(type: ToastMessage['type'], message: string, duration = 4000) {
  const id = `toast-${++toastId}`
  toasts.value.push({ id, type, message, duration })
  
  if (duration > 0) {
    setTimeout(() => removeToast(id), duration)
  }
}

function removeToast(id: string) {
  const index = toasts.value.findIndex(t => t.id === id)
  if (index > -1) {
    toasts.value.splice(index, 1)
  }
}

export function useToast() {
  return {
    success: (msg: string, duration?: number) => addToast('success', msg, duration),
    error: (msg: string, duration?: number) => addToast('error', msg, duration),
    warning: (msg: string, duration?: number) => addToast('warning', msg, duration),
    info: (msg: string, duration?: number) => addToast('info', msg, duration),
    remove: removeToast,
    toasts
  }
}
