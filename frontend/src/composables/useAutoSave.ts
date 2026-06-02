import { watch, onBeforeUnmount } from 'vue'
import type { WatchSource } from 'vue'

interface UseAutoSaveOptions {
  debounceMs?: number
  immediate?: boolean
}

export function useAutoSave(
  source: WatchSource,
  saveFn: () => Promise<void> | void,
  options: UseAutoSaveOptions = {}
) {
  const { debounceMs = 1000, immediate = false } = options
  let timer: ReturnType<typeof setTimeout> | null = null
  let isSaving = false

  function debouncedSave() {
    if (timer) clearTimeout(timer)
    timer = setTimeout(async () => {
      if (isSaving) return
      isSaving = true
      try {
        await saveFn()
      } finally {
        isSaving = false
      }
    }, debounceMs)
  }

  const stop = watch(source, debouncedSave, { deep: true, immediate })

  function flush() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    return saveFn()
  }

  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer)
    stop()
  })

  return { flush, stop }
}
