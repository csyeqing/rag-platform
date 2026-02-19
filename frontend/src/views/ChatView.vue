<template>
  <div class="grid gap-4 lg:grid-cols-[280px_1fr]">
    <el-card class="h-[74vh] overflow-hidden">
      <template #header>
        <div class="flex items-center justify-between">
          <span>会话</span>
          <el-button type="primary" link @click="newSession">新建</el-button>
        </div>
      </template>
      <div class="space-y-2 overflow-y-auto pr-1">
        <div
          v-for="item in sessions"
          :key="item.id"
          class="group flex w-full items-center justify-between rounded border px-3 py-2 text-left text-sm hover:bg-slate-50"
          :class="item.id === selectedSessionId ? 'border-cyan-500 bg-cyan-50' : 'border-slate-200'"
          @click="selectSession(item.id)"
        >
          <div>
            <div class="font-medium">{{ item.title }}</div>
            <div class="text-xs text-slate-500">{{ formatDate(item.updated_at) }}</div>
          </div>
          <el-button
            type="danger"
            link
            size="small"
            class="opacity-0 group-hover:opacity-100"
            @click.stop="handleDeleteSession(item.id)"
          >
            删除
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card class="h-[74vh] overflow-hidden">
      <template #header>
        <div class="grid gap-2 md:grid-cols-3">
          <el-select v-model="currentProviderId" placeholder="选择模型配置">
            <el-option
              v-for="item in providers"
              :key="item.id"
              :label="`${item.name} (${item.provider_type})`"
              :value="item.id"
            />
          </el-select>
          <el-select v-model="currentLibraryId" :disabled="libraryLocked" clearable placeholder="选择知识库">
            <el-option
              v-for="library in libraries"
              :key="library.id"
              :label="`${library.name} (${library.owner_type})`"
              :value="library.id"
            />
          </el-select>
          <div class="flex items-center justify-end gap-2">
            <el-switch v-model="showCitations" active-text="显示引用" />
            <el-switch v-model="useRerank" active-text="重排" />
          </div>
        </div>
      </template>

      <div class="flex h-full flex-col">
        <div class="flex-1 space-y-3 overflow-y-auto rounded-md bg-slate-50 p-3">
          <div
            v-for="message in messages"
            :key="message.id"
            class="rounded-lg p-3"
            :class="message.role === 'user' ? 'bg-cyan-100' : 'bg-white border border-slate-200'"
          >
            <div class="mb-1 text-xs uppercase text-slate-500">{{ message.role }}</div>
            <div class="whitespace-pre-wrap text-sm text-slate-700">{{ message.content }}</div>
            <div v-if="message.role === 'assistant' && message.citations?.length && showCitations" class="mt-3 space-y-2">
              <div class="text-xs font-medium text-slate-500">引用来源</div>
              <div v-for="citation in message.citations" :key="citation.chunk_id" class="rounded border border-slate-200 bg-slate-100 p-2 text-xs">
                <div>
                  {{ citation.file_name }} (score={{ Number(citation.score).toFixed(3) }}, source={{ citation.source }})
                </div>
                <div class="mt-1 text-slate-600">{{ citation.snippet }}</div>
                <div v-if="citation.matched_entities?.length" class="mt-1 text-slate-500">
                  图谱命中实体：{{ citation.matched_entities.join('、') }}
                </div>
              </div>
            </div>
          </div>
          <div v-if="streaming" class="rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <div class="mb-1 text-xs uppercase text-slate-500">assistant(stream)</div>
            <div class="whitespace-pre-wrap">{{ streamBuffer }}</div>
          </div>
        </div>

        <div class="mt-4 grid gap-2 md:grid-cols-[1fr_auto]">
          <el-input
            v-model="input"
            type="textarea"
            :rows="3"
            placeholder="输入问题，Enter 发送，Ctrl+Enter 换行"
            @keydown="handleInputKeydown"
          />
          <div class="flex flex-col gap-2">
            <el-button type="primary" :loading="streaming" @click="send">发送</el-button>
            <el-button plain @click="refreshMessages">刷新消息</el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  createSession,
  deleteSession,
  listLibraries,
  listMessages,
  listProviders,
  listSessions,
  streamChatMessage,
  updateSession,
} from '../api'
import type { ChatMessage, ChatSession, KnowledgeLibrary, ProviderConfig } from '../types'

const sessions = ref<ChatSession[]>([])
const providers = ref<ProviderConfig[]>([])
const libraries = ref<KnowledgeLibrary[]>([])
const messages = ref<ChatMessage[]>([])

const selectedSessionId = ref('')
const currentProviderId = ref('')
const currentLibraryId = ref('')
const input = ref('')
const libraryLocked = ref(false) // 知识库选择是否已锁定
const showCitations = ref(true)
const useRerank = ref(false)
const streaming = ref(false)
const streamBuffer = ref('')

function formatDate(value: string) {
  return new Date(value).toLocaleString()
}

function handleInputKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.ctrlKey) {
    event.preventDefault()
    send()
  }
  // Ctrl+Enter 默认行为就是换行，不需要处理
}

async function loadBasicData() {
  const [sessionRows, providerRows, libraryRows] = await Promise.all([
    listSessions(),
    listProviders(),
    listLibraries(),
  ])

  sessions.value = sessionRows
  providers.value = providerRows
  libraries.value = libraryRows

  if (!selectedSessionId.value && sessionRows.length > 0) {
    selectedSessionId.value = sessionRows[0]?.id ?? ''
  }
  if (!currentProviderId.value && providerRows.length > 0) {
    currentProviderId.value =
      providerRows.find((item) => item.is_default)?.id || providerRows[0]?.id || ''
  }

  if (selectedSessionId.value) {
    // 恢复当前会话的知识库选择
    const currentSession = sessionRows.find(s => s.id === selectedSessionId.value)
    if (currentSession?.library_id) {
      currentLibraryId.value = currentSession.library_id
    }
    // 恢复当前会话的模型配置
    if (currentSession?.provider_config_id) {
      currentProviderId.value = currentSession.provider_config_id
    }
    // 恢复当前会话的显示引用设置
    showCitations.value = currentSession?.show_citations ?? true
    await refreshMessages()
    // 如果会话已有消息，锁定知识库
    if (messages.value.length > 0) {
      libraryLocked.value = true
    }
  }
}

async function newSession() {
  const title = `会话 ${new Date().toLocaleTimeString()}`
  const created = await createSession({
    title,
    provider_config_id: currentProviderId.value || null,
    library_id: null,  // 新会话不绑定知识库
    show_citations: true,
  })
  // 保存到本地会话对象中，以便切换时恢复
  created.library_id = null
  created.show_citations = true
  sessions.value.unshift(created)
  selectedSessionId.value = created.id
  messages.value = []
  // 新会话未开始，清空知识库选择，允许选择知识库
  currentLibraryId.value = ''
  libraryLocked.value = false
  showCitations.value = true
}

async function selectSession(id: string) {
  // 切换会话前，保存当前会话的状态
  if (selectedSessionId.value) {
    const currentSession = sessions.value.find(s => s.id === selectedSessionId.value)
    if (currentSession) {
      currentSession.library_id = currentLibraryId.value
      currentSession.show_citations = showCitations.value
    }
  }
  
  selectedSessionId.value = id
  
  // 恢复新会话的状态
  const targetSession = sessions.value.find(s => s.id === id)
  if (targetSession) {
    currentLibraryId.value = targetSession.library_id || ''
    showCitations.value = targetSession.show_citations ?? true
  }
  
  if (targetSession?.library_id) {
    // 有绑定的知识库，检查是否有消息
    await refreshMessages()
    if (messages.value.length > 0) {
      libraryLocked.value = true
    } else {
      libraryLocked.value = false
    }
  } else {
    // 没有绑定知识库（直接和模型对话）
    currentLibraryId.value = ''
    await refreshMessages()
    // 如果已有消息，不允许再选知识库
    if (messages.value.length > 0) {
      libraryLocked.value = true
    } else {
      libraryLocked.value = false
    }
  }
}

async function handleDeleteSession(id: string) {
  try {
    await deleteSession(id)
    const index = sessions.value.findIndex((s) => s.id === id)
    if (index !== -1) {
      sessions.value.splice(index, 1)
    }
    if (selectedSessionId.value === id) {
      selectedSessionId.value = ''
      messages.value = []
    }
    ElMessage.success('会话已删除')
  } catch {
    ElMessage.error('删除失败')
  }
}

async function refreshMessages() {
  if (!selectedSessionId.value) {
    return
  }
  messages.value = await listMessages(selectedSessionId.value)
}

async function send() {
  if (!selectedSessionId.value) {
    await newSession()
  }
  if (!input.value.trim()) {
    return
  }

  const content = input.value.trim()
  input.value = ''
  messages.value.push({
    id: `local-user-${Date.now()}`,
    session_id: selectedSessionId.value,
    role: 'user',
    content,
    citations: [],
    created_at: new Date().toISOString(),
  })

  // 发送消息后锁定知识库选择，并保存到会话对象和数据库
  libraryLocked.value = true
  const currentSession = sessions.value.find(s => s.id === selectedSessionId.value)
  if (currentSession) {
    currentSession.library_id = currentLibraryId.value || null
    currentSession.show_citations = showCitations.value
    // 同步更新到数据库
    updateSession(selectedSessionId.value, {
      library_id: currentLibraryId.value || null,
      show_citations: showCitations.value,
    }).catch(() => {
      // 忽略更新失败
    })
  }
  
  const payload = {
    content,
    provider_config_id: currentProviderId.value || null,
    library_ids: currentLibraryId.value ? [currentLibraryId.value] : [],
    top_k: 5,
    use_rerank: useRerank.value,
    show_citations: showCitations.value,
    temperature: 0.2,
    top_p: 0.9,
    max_tokens: 4096,
  }

  streaming.value = true
  streamBuffer.value = ''

  const token = localStorage.getItem('rag_token') || ''
  if (!token) {
    ElMessage.error('登录态失效，请重新登录')
    return
  }

  streamChatMessage(
    selectedSessionId.value,
    token,
    payload,
    (delta) => {
      streamBuffer.value += delta
    },
    (citations) => {
      streaming.value = false
      messages.value.push({
        id: `local-assistant-${Date.now()}`,
        session_id: selectedSessionId.value,
        role: 'assistant',
        content: streamBuffer.value,
        citations: citations as any,
        created_at: new Date().toISOString(),
      })
      streamBuffer.value = ''
    },
    (message) => {
      streaming.value = false
      ElMessage.error(message)
    },
  )
}

onMounted(async () => {
  try {
    await loadBasicData()
    if (!selectedSessionId.value) {
      await newSession()
    }
  } catch {
    ElMessage.warning('聊天页初始化失败，请检查后端是否启动')
  }
})
</script>
