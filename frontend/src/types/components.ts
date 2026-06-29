export interface BaseComponentProps {
  id?: string
  class?: string
}

export interface StateViewProps {
  loading?: boolean
  error?: string | null
  isEmpty?: boolean
  onRetry?: () => void
}

export interface ThinkingBlockProps {
  content?: string
  isStreaming?: boolean
}

export interface ActionChip {
  label: string
  value?: string
}

export interface ActionChipsProps {
  chips: ActionChip[]
}

export interface ActionChipsEmits {
  (e: 'select', value: string): void
}

export interface AppDialogProps {
  open?: boolean
  title: string
  labelledById?: string
}

export interface AppDialogEmits {
  (e: 'close'): void
}

export interface ToolCall {
  name: string
  arguments?: string | Record<string, any>
  result?: string
  status?: 'running' | 'done' | string
}

export interface ToolCallBlockProps {
  toolCall: ToolCall
}

export interface DiffBlockChange {
  id: string | number
  [key: string]: any
}

export interface DiffBlockStore {
  acceptProposal: (id: string | number) => Promise<void>
  rejectProposal: (id: string | number) => Promise<void>
}

export interface DiffBlockProps {
  change: DiffBlockChange
  store: DiffBlockStore
  align?: string
}

export interface FileReviewCardProps {
  filename?: string
  wordCount?: number
  head?: string
  tail?: string
  suggestedKinds?: string[]
  fileId?: string | number | null
}

export interface FileReviewCardEmits {
  (e: 'pick', payload: { kind: string; fileId: string | number | null }): void
}

export interface ChartPreviewCardProps {
  url?: string
  spec?: Record<string, any> | null
  imageId?: string | number | null
  title?: string
}

export interface ChartPreviewCardEmits {
  (e: 'accept', payload: { imageId: string | number | null; spec: Record<string, any> | null; url: string }): void
  (e: 'regenerate', payload: { imageId: string | number | null; spec: Record<string, any> | null }): void
}

export interface QuestionOption {
  label: string
  value: string
  recommended?: boolean
}

export interface Question {
  key: string
  label: string
  options?: QuestionOption[]
}

export interface MultiQuestionCardProps {
  questions: Question[]
  isLoading?: boolean
}

export interface MultiQuestionAnswer {
  key: string
  value: string
}

export interface MultiQuestionCardEmits {
  (e: 'multi-question-submit', answers: MultiQuestionAnswer[]): void
}
