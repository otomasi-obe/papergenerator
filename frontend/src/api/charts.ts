import api from './index'

export interface ChartSpec {
  kind: 'line' | 'bar' | 'scatter' | 'hist' | 'box' | 'heatmap' | 'pie'
  title: string
  xlabel?: string
  ylabel?: string
  data: number[][]
  series_labels?: string[]
  x_data?: (string | number)[]
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

export const chartsApi = {
  async list(paperId: string): Promise<{ charts: Chart[] }> {
    const response = await api.get(`/api/papers/${paperId}/charts`)
    return response.data
  },

  async get(paperId: string, chartId: number): Promise<Chart> {
    const response = await api.get(`/api/papers/${paperId}/charts/${chartId}`)
    return response.data
  },

  async create(paperId: string, spec: ChartSpec): Promise<Chart> {
    const response = await api.post(`/api/papers/${paperId}/charts`, spec)
    return response.data
  },

  async update(paperId: string, chartId: number, spec: ChartSpec): Promise<Chart> {
    const response = await api.put(`/api/papers/${paperId}/charts/${chartId}`, spec)
    return response.data
  },

  async delete(paperId: string, chartId: number): Promise<void> {
    await api.delete(`/api/papers/${paperId}/charts/${chartId}`)
  },

  async uploadData(paperId: string, file: File): Promise<ParsedData> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await api.post(`/api/papers/${paperId}/charts/upload-data`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  }
}

export default chartsApi
