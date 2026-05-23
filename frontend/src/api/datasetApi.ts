import axios from 'axios'

export type DatasetMetadata = {
  dataset_id: string
  version_id: string
  file_name: string
  row_count: number
  column_count: number
  profile_status: string
  dashboard_status: string
  created_at: string
}

export type JobRecord<T = unknown> = {
  job_id: string
  job_type: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  payload: Record<string, unknown>
  result: T | null
  error: string
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
}

export type ProfileReport = {
  dataset_version_id: string
  row_count: number
  column_count: number
  columns: Array<{
    name: string
    data_type: string
    null_count: number
    null_ratio: number
    unique_count: number
    cardinality_ratio: number
    sample_values: Array<string | number | boolean | null>
    is_numeric: boolean
    is_datetime: boolean
    is_probable_index: boolean
    is_probable_identifier: boolean
    is_constant: boolean
  }>
  quality_issues: Array<{
    type: string
    severity?: 'low' | 'medium' | 'high'
    column: string | null
    count?: number
    message: string
  }>
}

export type DatasetPreview = {
  columns: string[]
  rows: Array<Record<string, string | number | boolean | null>>
}

export type CleaningOperation = {
  id: string
  operation_type: string
  target_column: string | null
  parameters: Record<string, string | number | boolean | string[] | null>
  rationale: string
  enabled: boolean
}

export type CleaningPlan = {
  dataset_id: string
  version_id: string
  operation_count: number
  operations: CleaningOperation[]
}

export type CleaningPreview = {
  plan: CleaningPlan
  before: DatasetPreview
  after: DatasetPreview
  row_count_delta: number
  column_count_delta: number
}

export type DashboardDraft = {
  id: string
  title: string
  file_name?: string
  dataset_id: string
  version_id: string
  status: string
  analysis_source?: string
  report?: {
    title: string
    executive_summary: string
    sections: Array<{ title: string; body: string }>
    next_actions: string[]
    source: string
    generated_at: string
  } | null
  cards: Array<{
    id: string
    type: string
    title: string
    value?: number | string
    items?: Array<{ title: string; body: string }>
    chart_type?: string
    encoding?: Record<string, string>
    layout?: { size?: 'compact' | 'standard' | 'wide' | 'tall' | 'hero' }
    rationale?: string
    data?: Array<{
      label: string
      value?: number
      x?: number
      y?: number
      xLabel?: string
      yLabel?: string
      target?: number
      marker?: number
      min?: number
      q1?: number
      median?: number
      q3?: number
      max?: number
    }>
  }>
}

export type DashboardReport = NonNullable<DashboardDraft['report']>

export const importDatasetFile = async (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  const response = await axios.post('/api/v1/datasets/import/file', formData)
  return response.data as DatasetMetadata
}

export const createImportDatasetJob = async (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  const response = await axios.post('/api/v1/datasets/import/file/job', formData)
  return response.data as JobRecord<DatasetMetadata>
}

export const getJob = async <T = unknown>(jobId: string) => {
  const response = await axios.get(`/api/v1/jobs/${jobId}`)
  return response.data as JobRecord<T>
}

export const listDatasets = async () => {
  const response = await axios.get('/api/v1/datasets')
  return response.data as DatasetMetadata[]
}

export const getDatasetProfile = async (datasetId: string, versionId: string) => {
  const response = await axios.get(`/api/v1/datasets/${datasetId}/versions/${versionId}/profile`)
  return response.data as ProfileReport
}

export const getDatasetPreview = async (datasetId: string, versionId: string, limit = 50) => {
  const response = await axios.get(`/api/v1/datasets/${datasetId}/versions/${versionId}/preview`, {
    params: { limit }
  })
  return response.data as DatasetPreview
}

export const getCleaningPlan = async (datasetId: string, versionId: string) => {
  const response = await axios.get(`/api/v1/datasets/${datasetId}/versions/${versionId}/cleaning-plan`)
  return response.data as CleaningPlan
}

export const previewCleaning = async (datasetId: string, versionId: string, operationIds?: string[]) => {
  const response = await axios.post(`/api/v1/datasets/${datasetId}/versions/${versionId}/cleaning-preview`, {
    operation_ids: operationIds ?? null
  })
  return response.data as CleaningPreview
}

export const createCleaningJob = async (datasetId: string, versionId: string, operationIds?: string[]) => {
  const response = await axios.post(`/api/v1/datasets/${datasetId}/versions/${versionId}/cleaning-execute/job`, {
    operation_ids: operationIds ?? null
  })
  return response.data as JobRecord<DatasetMetadata>
}

export const executeCleaning = async (datasetId: string, versionId: string, operationIds?: string[]) => {
  const response = await axios.post(`/api/v1/datasets/${datasetId}/versions/${versionId}/cleaning-execute`, {
    operation_ids: operationIds ?? null
  })
  return response.data as DatasetMetadata
}

export const listDashboards = async () => {
  const response = await axios.get('/api/v1/dashboards')
  return response.data as DashboardDraft[]
}

export const generateDashboardReport = async (datasetId: string, versionId: string) => {
  const response = await axios.post(`/api/v1/dashboards/by-dataset/${datasetId}/versions/${versionId}/report`)
  return response.data as DashboardReport
}

export const createDashboardReportJob = async (datasetId: string, versionId: string) => {
  const response = await axios.post(`/api/v1/dashboards/by-dataset/${datasetId}/versions/${versionId}/report/job`)
  return response.data as JobRecord<DashboardReport>
}

export const deleteDatasetVersion = async (datasetId: string, versionId: string) => {
  const response = await axios.delete(`/api/v1/dashboards/by-dataset/${datasetId}/versions/${versionId}`)
  return response.data as { deleted: boolean }
}

export const getLlmConfig = async () => {
  const response = await axios.get('/api/v1/llm/config')
  return response.data as {
    provider: string
    base_url: string
    model: string
    api_key_configured: boolean
  }
}

export const getLlmHealth = async () => {
  const response = await axios.get('/api/v1/llm/health')
  return response.data as {
    status: 'ok' | 'error'
    provider: string
    base_url: string
    model: string
    api_key_configured: boolean
    latency_ms: number
    sample: string
    error: string
  }
}
