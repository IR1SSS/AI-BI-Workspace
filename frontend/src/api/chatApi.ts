import axios from 'axios'

export type DatasetChatResponse = {
  answer: string
  sql: string
  rows: Array<Record<string, string | number | boolean | null>>
  source: string
  error?: string
  messages: DatasetChatMessage[]
}

export type DatasetChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  sql?: string
  rows?: Array<Record<string, string | number | boolean | null>>
  source?: string
  error?: string
}

export type DatasetChatSuggestions = {
  source: string
  suggestions: string[]
  error?: string
}

export const askDatasetQuestion = async (
  datasetId: string,
  versionId: string,
  question: string
) => {
  const response = await axios.post(
    `/api/v1/chat/datasets/${datasetId}/versions/${versionId}/messages`,
    { question }
  )
  return response.data as DatasetChatResponse
}

export const listDatasetChatMessages = async (datasetId: string, versionId: string) => {
  const response = await axios.get(`/api/v1/chat/datasets/${datasetId}/versions/${versionId}/messages`)
  return response.data as DatasetChatMessage[]
}

export const listDatasetChatSuggestions = async (datasetId: string, versionId: string) => {
  const response = await axios.get(`/api/v1/chat/datasets/${datasetId}/versions/${versionId}/suggestions`)
  return response.data as DatasetChatSuggestions
}

export const deleteDatasetChatMessages = async (datasetId: string, versionId: string) => {
  const response = await axios.delete(`/api/v1/chat/datasets/${datasetId}/versions/${versionId}/messages`)
  return response.data as { deleted: boolean }
}
