import api from './index'

export interface ChartSpec {
  kind: string
  title: string
  xlabel?: string
  ylabel?: string
  data: number[][]
  series_labels?: string[]
  x_data?: (string | number)[]
  // Styling
  color_palette?: string
  custom_colors?: string[]
  theme?: string
  font_size?: number
  title_font_size?: number
  show_grid?: boolean
  show_legend?: boolean
  legend_position?: string
  bar_width?: number
  line_width?: number
  marker_size?: number
  show_data_labels?: boolean
  rotation_x?: number
  figsize?: [number, number]
  dpi?: number
}

export interface Chart {
  image_id: number
  filename: string
  url: string
  kind: string
  paper_id?: string
  original_name?: string
  created_at?: string
}

export interface ParsedData {
  columns: string[]
  rows: (string | number)[][]
  n_rows: number
  preview: string
  filename: string
}

export interface ChartKindInfo {
  label: string
  icon: string
  category: string
}

export interface PreviewResponse {
  image: string  // base64 data URI
  kind: string
}

export interface AITable {
  name: string
  description: string
  columns: string[]
  rows: (string | number)[][]
  column_types: string[]
  data_quality?: {
    total_rows: number
    missing_values: number
    notes: string
  }
}

export interface AIChartRecommendation {
  kind: string
  title: string
  reason: string
  table_index: number
  x_column: string
  y_columns: string[]
  suggested_settings?: {
    color_palette?: string
    theme?: string
    show_data_labels?: boolean
  }
}

export interface AIFormatResult {
  tables: AITable[]
  chart_recommendations: AIChartRecommendation[]
  summary: {
    data_overview: string
    analysis: string
  }
  _model_used?: string
}

export const chartsApi = {
  async list(paperId: string): Promise<{ charts: Chart[] }> {
    try { return await (await api.get(`/api/papers/${paperId}/charts`)).data } catch (e) { console.error('[charts] list', e); throw e }
  },

  async get(paperId: string, chartId: number): Promise<Chart> {
    try { return await (await api.get(`/api/papers/${paperId}/charts/${chartId}`)).data } catch (e) { console.error('[charts] get', e); throw e }
  },

  async create(paperId: string, spec: ChartSpec): Promise<Chart> {
    try { return await (await api.post(`/api/papers/${paperId}/charts`, spec)).data } catch (e) { console.error('[charts] create', e); throw e }
  },

  async update(paperId: string, chartId: number, spec: ChartSpec): Promise<Chart> {
    try { return await (await api.put(`/api/papers/${paperId}/charts/${chartId}`, spec)).data } catch (e) { console.error('[charts] update', e); throw e }
  },

  async delete(paperId: string, chartId: number): Promise<void> {
    try { await api.delete(`/api/papers/${paperId}/charts/${chartId}`) } catch (e) { console.error('[charts] delete', e); throw e }
  },

  async preview(paperId: string, spec: ChartSpec): Promise<PreviewResponse> {
    try { return await (await api.post(`/api/papers/${paperId}/charts/preview`, spec)).data } catch (e) { console.error('[charts] preview', e); throw e }
  },

  async getKinds(paperId: string): Promise<{ kinds: Record<string, ChartKindInfo> }> {
    try { return await (await api.get(`/api/papers/${paperId}/charts/kinds`)).data } catch (e) { console.error('[charts] getKinds', e); throw e }
  },

  async getPalettes(paperId: string): Promise<{ palettes: Record<string, string[]> }> {
    try { return await (await api.get(`/api/papers/${paperId}/charts/palettes`)).data } catch (e) { console.error('[charts] getPalettes', e); throw e }
  },

  async uploadData(paperId: string, file: File): Promise<ParsedData> {
    try {
      const formData = new FormData()
      formData.append('file', file)
      return await (await api.post(`/api/papers/${paperId}/charts/upload-data`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })).data
    } catch (e) { console.error('[charts] uploadData', e); throw e }
  },

  /**
   * Format data dengan AI: upload file → extract → AI → tabel + rekomendasi grafik.
   * Bisa file upload atau text langsung.
   */
  async aiFormat(paperId: string, fileOrText: File | string): Promise<AIFormatResult> {
    try {
      if (fileOrText instanceof File) {
        const formData = new FormData()
        formData.append('file', fileOrText)
        return await (await api.post(`/api/papers/${paperId}/charts/ai-format`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 120000 // 2 menit timeout untuk AI processing
        })).data
      } else {
        return await (await api.post(`/api/papers/${paperId}/charts/ai-format`, {
          text: fileOrText
        }, {
          timeout: 120000
        })).data
      }
    } catch (e) { console.error('[charts] aiFormat', e); throw e }
  }
}

export default chartsApi
