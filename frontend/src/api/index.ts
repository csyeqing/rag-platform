import apiClient from './client'
import type {
  ChatMessage,
  ChatSession,
  KnowledgeFile,
  KnowledgeGraphRebuildResult,
  KnowledgeGraphSnapshot,
  KnowledgeLibrary,
  LoginResponse,
  ProviderConfig,
  RetrievalProfile,
  UserListItem,
  UserMe,
} from '../types'

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await apiClient.post('/auth/login', { username, password })
  return data
}

export async function getCurrentUser(): Promise<UserMe> {
  const { data } = await apiClient.get('/users/me')
  return data
}

export async function listProviders(): Promise<ProviderConfig[]> {
  const { data } = await apiClient.get('/providers')
  return data
}

export async function createProvider(payload: Record<string, unknown>): Promise<ProviderConfig> {
  const { data } = await apiClient.post('/providers', payload)
  return data
}

export async function updateProvider(id: string, payload: Record<string, unknown>): Promise<ProviderConfig> {
  const { data } = await apiClient.put(`/providers/${id}`, payload)
  return data
}

export async function deleteProvider(id: string): Promise<void> {
  await apiClient.delete(`/providers/${id}`)
}

export async function validateModel(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/models/validate', payload)
  return data
}

export async function listLibraries(): Promise<KnowledgeLibrary[]> {
  const { data } = await apiClient.get('/kb/libraries')
  return data
}

export async function createLibrary(payload: Record<string, unknown>): Promise<KnowledgeLibrary> {
  const { data } = await apiClient.post('/kb/libraries', payload)
  return data
}

export async function updateLibrary(
  libraryId: string,
  payload: Record<string, unknown>,
): Promise<KnowledgeLibrary> {
  const { data } = await apiClient.put(`/kb/libraries/${libraryId}`, payload)
  return data
}

export async function deleteLibrary(libraryId: string): Promise<void> {
  await apiClient.delete(`/kb/libraries/${libraryId}`)
}

export async function listLibraryFiles(libraryId: string): Promise<KnowledgeFile[]> {
  const { data } = await apiClient.get(`/kb/libraries/${libraryId}/files`)
  return data
}

export async function deleteLibraryFile(fileId: string): Promise<void> {
  await apiClient.delete(`/kb/files/${fileId}`)
}

export async function getLibraryGraph(
  libraryId: string,
  params?: { limit_nodes?: number; limit_edges?: number },
): Promise<KnowledgeGraphSnapshot> {
  const { data } = await apiClient.get(`/kb/libraries/${libraryId}/graph`, { params })
  return data
}

export async function rebuildLibraryGraph(libraryId: string): Promise<KnowledgeGraphRebuildResult> {
  const { data } = await apiClient.post(`/kb/libraries/${libraryId}/graph/rebuild`)
  return data
}

export async function syncDirectory(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/kb/files/sync-directory', payload)
  return data
}

export async function rebuildIndex(payload: Record<string, unknown>) {
  const { data } = await apiClient.post('/kb/index/rebuild', payload)
  return data
}

export async function uploadFile(
  libraryId: string,
  file: File,
  onProgress?: (percent: number) => void
) {
  const form = new FormData()
  form.append('library_id', libraryId)
  form.append('file', file)
  const { data } = await apiClient.post('/kb/files/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    },
  })
  return data
}

export async function listSessions(): Promise<ChatSession[]> {
  const { data } = await apiClient.get('/chat/sessions')
  return data
}

export async function createSession(payload: Record<string, unknown>): Promise<ChatSession> {
  const { data } = await apiClient.post('/chat/sessions', payload)
  return data
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiClient.delete(`/chat/sessions/${sessionId}`)
}

export async function updateSession(sessionId: string, payload: Record<string, unknown>): Promise<ChatSession> {
  const { data } = await apiClient.patch(`/chat/sessions/${sessionId}`, payload)
  return data
}

export async function listMessages(sessionId: string): Promise<ChatMessage[]> {
  const { data } = await apiClient.get(`/chat/sessions/${sessionId}/messages`)
  return data.items
}

export async function listUsers(): Promise<UserListItem[]> {
  const { data } = await apiClient.get('/admin/users')
  return data
}

export async function listRetrievalProfiles(): Promise<RetrievalProfile[]> {
  const { data } = await apiClient.get('/settings/retrieval-profiles')
  return data
}

export async function createRetrievalProfile(payload: Record<string, unknown>): Promise<RetrievalProfile> {
  const { data } = await apiClient.post('/settings/retrieval-profiles', payload)
  return data
}

export async function updateRetrievalProfile(
  profileId: string,
  payload: Record<string, unknown>,
): Promise<RetrievalProfile> {
  const { data } = await apiClient.put(`/settings/retrieval-profiles/${profileId}`, payload)
  return data
}

export async function deleteRetrievalProfile(profileId: string): Promise<void> {
  await apiClient.delete(`/settings/retrieval-profiles/${profileId}`)
}

export async function createUser(payload: Record<string, unknown>): Promise<UserListItem> {
  const { data } = await apiClient.post('/admin/users', payload)
  return data
}

export async function updateUser(userId: string, payload: Record<string, unknown>): Promise<UserListItem> {
  const { data } = await apiClient.put(`/admin/users/${userId}`, payload)
  return data
}

export async function sendChatMessage(
  sessionId: string,
  payload: Record<string, unknown>,
): Promise<{ content: string; citations: unknown[] }> {
  const { data } = await apiClient.post(`/chat/sessions/${sessionId}/messages`, {
    ...payload,
    stream: false,
  })
  return data
}

export function streamChatMessage(
  sessionId: string,
  token: string,
  payload: Record<string, unknown>,
  onDelta: (delta: string) => void,
  onDone: (citations: unknown[]) => void,
  onError: (message: string) => void,
) {
  fetch(`${apiClient.defaults.baseURL}/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ ...payload, stream: true }),
  })
    .then(async (response) => {
      if (!response.ok || !response.body) {
        throw new Error(`stream failed: ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      let finalCitations: unknown[] = []

      try {
        while (true) {
          const { value, done } = await reader.read()
          if (done) {
            break
          }
          buffer += decoder.decode(value, { stream: true })
          const chunks = buffer.split('\n\n')
          buffer = chunks.pop() || ''

          for (const chunk of chunks) {
            const line = chunk.trim()
            if (!line.startsWith('data:')) {
              continue
            }
            const raw = line.slice(5).trim()
            if (!raw) continue
            try {
              const event = JSON.parse(raw)
              if (event.type === 'delta') {
                onDelta(event.delta)
              }
              if (event.type === 'done') {
                finalCitations = event.citations || []
              }
            } catch (e) {
              // ignore parse errors for individual chunks
            }
          }
        }
        onDone(finalCitations)
      } catch (err) {
        // stream reading error
        console.error('Stream read error:', err)
        onError(err instanceof Error ? err.message : 'stream error')
      }
    })
    .catch((err) => {
      console.error('Fetch error:', err)
      onError(err.message || 'stream error')
    })
}
