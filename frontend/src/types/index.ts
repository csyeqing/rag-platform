export type UserRole = 'admin' | 'user'

export interface LoginResponse {
  token: {
    access_token: string
    token_type: string
  }
  role: UserRole
  username: string
}

export interface UserMe {
  id: string
  username: string
  role: UserRole
  is_active: boolean
  created_at: string
}

export interface UserListItem {
  id: string
  username: string
  role: UserRole
  is_active: boolean
  created_at: string
}

export interface ProviderConfig {
  id: string
  name: string
  provider_type: string
  endpoint_url: string
  model_name: string
  is_default: boolean
  capabilities: Record<string, unknown>
  owner_id: string
  api_key_masked: string
  created_at: string
  updated_at: string
}

export interface KnowledgeLibrary {
  id: string
  name: string
  description: string | null
  owner_type: 'private' | 'shared'
  owner_id: string | null
  tags: string[]
  root_path: string
  created_at: string
  updated_at: string
}

export interface ChatSession {
  id: string
  user_id: string
  title: string
  provider_config_id: string | null
  library_id: string | null
  show_citations: boolean
  created_at: string
  updated_at: string
}

export interface Citation {
  library_id: string
  file_id: string
  file_name: string
  chunk_id: string
  score: number
  snippet: string
  source: string
  matched_entities?: string[]
}

export interface ChatMessage {
  id: string
  session_id: string
  role: 'system' | 'user' | 'assistant'
  content: string
  citations: Citation[]
  created_at: string
}

export interface KnowledgeFile {
  id: string
  library_id: string
  filename: string
  filepath: string
  file_type: string
  status: string
  created_at: string
  updated_at: string
}

export interface KnowledgeGraphNode {
  id: string
  name: string
  display_name: string
  entity_type: string
  frequency: number
}

export interface KnowledgeGraphEdge {
  id: string
  source_entity_id: string
  source_entity: string
  target_entity_id: string
  target_entity: string
  relation_type: string
  weight: number
}

export interface KnowledgeGraphSnapshot {
  library_id: string
  node_count: number
  edge_count: number
  nodes: KnowledgeGraphNode[]
  edges: KnowledgeGraphEdge[]
}

export interface KnowledgeGraphRebuildResult {
  library_id: string
  node_count: number
  edge_count: number
  chunk_count: number
  message: string
}
