export interface SlrJob {
  id: string
  paper_id: string
  user_id: number
  conversation_id?: string | null
  query: string
  sources?: string[] | null
  per_source: number
  top_k: number
  year_from?: number | null
  ai_summarize: boolean
  ai_model: string
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  stage?: string
  progress?: number
  error_message?: string | null
  result?: SlrResult | null
  queued_at: string
  started_at?: string | null
  finished_at?: string | null
  updated_at: string
}

export interface SlrResult {
  query: string
  top_k: number
  total_found: number
  sources: Record<string, SourceResult>
  top_papers: LiteraturePaper[]
  summary?: string
}

export interface SourceResult {
  count: number
  papers: LiteraturePaper[]
  error?: string
}

export interface LiteraturePaper {
  title: string
  authors: string[]
  year?: number | null
  venue?: string
  publisher?: string
  doi?: string | null
  url?: string | null
  abstract?: string
  summary?: string
  citations?: number | null
  score_total?: number | null
  score_breakdown?: Record<string, number>
  source: string
  source_id?: string
}

export interface LiteratureItem {
  id: number
  paper_id: string
  user_id: number
  source_kind: 'slr' | 'manual' | 'file'
  source: string
  title: string
  authors: string[]
  year?: number | null
  venue?: string
  publisher?: string
  doi?: string | null
  url?: string | null
  abstract?: string
  summary?: string
  citations?: number | null
  score_total?: number | null
  score_breakdown?: Record<string, number>
  must_read: boolean
  is_relevant: boolean
  notes?: string
  pinned: boolean
  slr_job_id?: string | null
  file_id?: number | null
  created_at: string
  updated_at: string
}

export interface CreateSlrJobRequest {
  query: string
  sources?: string[]
  per_source?: number
  top_k?: number
  year_from?: number
  ai_summarize?: boolean
  ai_model?: string
  conversation_id?: string
}

export interface LiteratureListResponse {
  items: LiteratureItem[]
  total: number
  page: number
  page_size: number
}
