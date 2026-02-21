<template>
  <div class="space-y-4">
    <el-card>
      <template #header>
        <span>系统设置（本地偏好）</span>
      </template>

      <el-form label-width="180px">
        <el-form-item label="默认语言">
          <el-select v-model="settings.language">
            <el-option label="中文" value="zh-CN" />
          </el-select>
        </el-form-item>
        <el-form-item label="聊天默认显示引用">
          <el-switch v-model="settings.defaultShowCitations" />
        </el-form-item>
        <el-form-item label="检索 TopK">
          <el-input-number v-model="settings.defaultTopK" :min="1" :max="20" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">保存到本地</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <span>知识库优化配置</span>
          <div class="flex items-center gap-2">
            <el-button text @click="loadRetrievalProfiles">刷新</el-button>
            <el-button
              v-if="auth.role === 'admin'"
              type="primary"
              @click="openCreateProfile"
            >
              新建配置
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="retrievalProfiles" stripe>
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="profile_type" label="类型" width="140">
          <template #default="{ row }">{{ profileTypeLabel(row.profile_type) }}</template>
        </el-table-column>
        <el-table-column prop="profile_key" label="Key" min-width="130" />
        <el-table-column label="阈值摘要" min-width="260">
          <template #default="{ row }">
            <div class="text-xs text-slate-600">
              top1={{ row.config.rag_min_top1_score }},
              support={{ row.config.rag_min_support_score }}/{{ row.config.rag_min_support_count }},
              item={{ row.config.rag_min_item_score }},
              graph_terms={{ row.config.rag_graph_max_terms }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="220">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" class="mr-1">默认</el-tag>
            <el-tag v-if="row.is_builtin" type="info" class="mr-1">内置</el-tag>
            <el-tag :type="row.is_active ? 'primary' : 'warning'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="auth.role === 'admin'" label="操作" width="220">
          <template #default="{ row }">
            <el-button size="small" link @click="openEditProfile(row)">编辑</el-button>
            <el-button size="small" link @click="setDefaultProfile(row)">设为默认</el-button>
            <el-button
              size="small"
              type="danger"
              link
              :disabled="row.is_builtin"
              @click="handleDeleteProfile(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="auth.role === 'admin'">
      <template #header>
        <div class="flex items-center justify-between">
          <span>用户管理（管理员）</span>
          <el-button text @click="loadUsers">刷新</el-button>
        </div>
      </template>

      <div class="mb-4 grid gap-3 md:grid-cols-4">
        <el-input v-model="createUserForm.username" placeholder="新用户名" />
        <el-input v-model="createUserForm.password" show-password type="password" placeholder="初始密码" />
        <el-select v-model="createUserForm.role">
          <el-option label="普通用户" value="user" />
          <el-option label="管理员" value="admin" />
        </el-select>
        <el-button type="primary" @click="handleCreateUser">创建用户</el-button>
      </div>

      <el-table :data="users" stripe>
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="role" label="角色" width="120" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="180" />
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button size="small" link @click="toggleUserActive(row.id, !row.is_active)">
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button
              size="small"
              link
              @click="toggleUserRole(row.id, row.role === 'admin' ? 'user' : 'admin')"
            >
              设为{{ row.role === 'admin' ? '普通用户' : '管理员' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="profileDialogVisible"
      :title="profileForm.id ? '编辑优化配置' : '新建优化配置'"
      width="760px"
      destroy-on-close
    >
      <el-form label-width="170px" class="grid grid-cols-1 gap-x-4 md:grid-cols-2">
        <el-form-item label="名称">
          <el-input v-model="profileForm.name" />
        </el-form-item>
        <el-form-item label="Key">
          <el-input v-model="profileForm.profile_key" :disabled="profileForm.is_builtin" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="profileForm.profile_type">
            <el-option v-for="item in profileTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="profileForm.is_active" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="profileForm.is_default" />
        </el-form-item>
        <el-form-item label="描述" class="md:col-span-2">
          <el-input v-model="profileForm.description" type="textarea" :rows="2" />
        </el-form-item>

        <el-form-item label="top1阈值">
          <el-input-number v-model="profileForm.config.rag_min_top1_score" :step="0.01" :min="0" :max="1.5" />
        </el-form-item>
        <el-form-item label="support阈值">
          <el-input-number v-model="profileForm.config.rag_min_support_score" :step="0.01" :min="0" :max="1.5" />
        </el-form-item>
        <el-form-item label="support数量">
          <el-input-number v-model="profileForm.config.rag_min_support_count" :min="1" :max="8" />
        </el-form-item>
        <el-form-item label="item阈值">
          <el-input-number v-model="profileForm.config.rag_min_item_score" :step="0.01" :min="0" :max="1.5" />
        </el-form-item>
        <el-form-item label="图谱扩展词上限">
          <el-input-number v-model="profileForm.config.rag_graph_max_terms" :min="4" :max="40" />
        </el-form-item>
        <el-form-item label="图谱通道权重">
          <el-input-number v-model="profileForm.config.graph_channel_weight" :step="0.01" :min="0.1" :max="1.2" />
        </el-form-item>
        <el-form-item label="图谱独立降权">
          <el-input-number v-model="profileForm.config.graph_only_penalty" :step="0.01" :min="0.1" :max="1.0" />
        </el-form-item>
        <el-form-item label="向量最小语义值">
          <el-input-number v-model="profileForm.config.vector_semantic_min" :step="0.01" :min="0" :max="1.0" />
        </el-form-item>
        <el-form-item label="启用外号意图">
          <el-switch v-model="profileForm.config.alias_intent_enabled" />
        </el-form-item>
        <el-form-item label="外号扩展上限">
          <el-input-number v-model="profileForm.config.alias_mining_max_terms" :min="0" :max="24" />
        </el-form-item>
        <el-form-item label="启用代词指代">
          <el-switch v-model="profileForm.config.co_reference_enabled" />
        </el-form-item>
        <el-form-item label="向量候选倍数">
          <el-input-number v-model="profileForm.config.vector_candidate_multiplier" :min="2" :max="20" />
        </el-form-item>
        <el-form-item label="关键词候选倍数">
          <el-input-number v-model="profileForm.config.keyword_candidate_multiplier" :min="2" :max="20" />
        </el-form-item>
        <el-form-item label="图谱候选倍数">
          <el-input-number v-model="profileForm.config.graph_candidate_multiplier" :min="2" :max="24" />
        </el-form-item>
        <el-form-item label="启用分级回退">
          <el-switch v-model="profileForm.config.fallback_relax_enabled" />
        </el-form-item>
        <el-form-item label="回退 top1 放宽">
          <el-input-number v-model="profileForm.config.fallback_top1_relax" :step="0.01" :min="0" :max="0.3" />
        </el-form-item>
        <el-form-item label="回退 support 放宽">
          <el-input-number v-model="profileForm.config.fallback_support_relax" :step="0.01" :min="0" :max="0.3" />
        </el-form-item>
        <el-form-item label="回退 item 放宽">
          <el-input-number v-model="profileForm.config.fallback_item_relax" :step="0.01" :min="0" :max="0.2" />
        </el-form-item>
        <el-form-item label="启用全盘总结模式">
          <el-switch v-model="profileForm.config.summary_intent_enabled" />
        </el-form-item>
        <el-form-item label="总结扩展倍数">
          <el-input-number v-model="profileForm.config.summary_expand_factor" :min="1" :max="8" />
        </el-form-item>
        <el-form-item label="总结最少片段">
          <el-input-number v-model="profileForm.config.summary_min_chunks" :min="4" :max="24" />
        </el-form-item>
        <el-form-item label="总结单文档上限">
          <el-input-number v-model="profileForm.config.summary_per_file_cap" :min="1" :max="6" />
        </el-form-item>
        <el-form-item label="总结最少文档数">
          <el-input-number v-model="profileForm.config.summary_min_files" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="兜底扩展弱命中">
          <el-switch v-model="profileForm.config.keyword_fallback_expand_on_weak_hits" />
        </el-form-item>
        <el-form-item label="兜底最大片段数">
          <el-input-number v-model="profileForm.config.keyword_fallback_max_chunks" :min="20" :max="800" />
        </el-form-item>
        <el-form-item label="兜底最低分数">
          <el-input-number v-model="profileForm.config.keyword_fallback_min_score" :step="0.01" :min="0" :max="1.5" />
        </el-form-item>
        <el-form-item label="兜底扫描上限">
          <el-input-number v-model="profileForm.config.keyword_fallback_scan_limit" :step="100" :min="200" :max="20000" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="profileDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitProfile">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createRetrievalProfile,
  createUser,
  deleteRetrievalProfile,
  listRetrievalProfiles,
  listUsers,
  updateRetrievalProfile,
  updateUser,
} from '../api'
import { useAuthStore } from '../stores/auth'
import type { RetrievalProfile, RetrievalProfileConfig, UserListItem } from '../types'

const auth = useAuthStore()

const settings = reactive({
  language: localStorage.getItem('rag_setting_language') || 'zh-CN',
  defaultShowCitations: localStorage.getItem('rag_setting_show_citations') !== '0',
  defaultTopK: Number(localStorage.getItem('rag_setting_top_k') || '5'),
})

const users = ref<UserListItem[]>([])
const retrievalProfiles = ref<RetrievalProfile[]>([])
const profileDialogVisible = ref(false)
const profileTypeOptions = [
  { value: 'general', label: '通用' },
  { value: 'novel_story', label: '小说/故事' },
  { value: 'enterprise_docs', label: '公司资料' },
  { value: 'scientific_paper', label: '科学论文' },
  { value: 'humanities_paper', label: '文科论文' },
]

const createUserForm = reactive({
  username: '',
  password: '',
  role: 'user',
})

function makeDefaultConfig(): RetrievalProfileConfig {
  return {
    rag_min_top1_score: 0.3,
    rag_min_support_score: 0.18,
    rag_min_support_count: 2,
    rag_min_item_score: 0.1,
    rag_graph_max_terms: 12,
    graph_channel_weight: 0.65,
    graph_only_penalty: 0.55,
    vector_semantic_min: 0.12,
    alias_intent_enabled: true,
    alias_mining_max_terms: 8,
    co_reference_enabled: true,
    vector_candidate_multiplier: 3,
    keyword_candidate_multiplier: 3,
    graph_candidate_multiplier: 4,
    fallback_relax_enabled: true,
    fallback_top1_relax: 0.08,
    fallback_support_relax: 0.06,
    fallback_item_relax: 0.04,
    summary_intent_enabled: true,
    summary_expand_factor: 3,
    summary_min_chunks: 8,
    summary_per_file_cap: 2,
    summary_min_files: 3,
    keyword_fallback_expand_on_weak_hits: true,
    keyword_fallback_max_chunks: 240,
    keyword_fallback_min_score: 0.08,
    keyword_fallback_scan_limit: 8000,
  }
}

const profileForm = reactive({
  id: '',
  profile_key: '',
  name: '',
  profile_type: 'general',
  description: '',
  is_default: false,
  is_builtin: false,
  is_active: true,
  config: makeDefaultConfig(),
})

function profileTypeLabel(value: RetrievalProfile['profile_type']) {
  const match = profileTypeOptions.find((item) => item.value === value)
  return match?.label || value
}

function save() {
  localStorage.setItem('rag_setting_language', settings.language)
  localStorage.setItem('rag_setting_show_citations', settings.defaultShowCitations ? '1' : '0')
  localStorage.setItem('rag_setting_top_k', String(settings.defaultTopK))
  ElMessage.success('已保存到本地配置')
}

async function loadUsers() {
  if (auth.role !== 'admin') {
    return
  }
  try {
    users.value = await listUsers()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '用户列表加载失败')
  }
}

async function loadRetrievalProfiles() {
  try {
    retrievalProfiles.value = await listRetrievalProfiles()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '检索配置加载失败')
  }
}

function resetProfileForm() {
  profileForm.id = ''
  profileForm.profile_key = ''
  profileForm.name = ''
  profileForm.profile_type = 'general'
  profileForm.description = ''
  profileForm.is_default = false
  profileForm.is_builtin = false
  profileForm.is_active = true
  profileForm.config = makeDefaultConfig()
}

function openCreateProfile() {
  resetProfileForm()
  profileDialogVisible.value = true
}

function openEditProfile(item: RetrievalProfile) {
  profileForm.id = item.id
  profileForm.profile_key = item.profile_key
  profileForm.name = item.name
  profileForm.profile_type = item.profile_type
  profileForm.description = item.description || ''
  profileForm.is_default = item.is_default
  profileForm.is_builtin = item.is_builtin
  profileForm.is_active = item.is_active
  profileForm.config = { ...item.config }
  profileDialogVisible.value = true
}

async function submitProfile() {
  if (!profileForm.name.trim() || !profileForm.profile_key.trim()) {
    ElMessage.warning('请填写名称和 Key')
    return
  }

  const payload = {
    profile_key: profileForm.profile_key.trim(),
    name: profileForm.name.trim(),
    profile_type: profileForm.profile_type,
    description: profileForm.description?.trim() || null,
    is_default: profileForm.is_default,
    is_active: profileForm.is_active,
    config: profileForm.config,
  }

  try {
    if (profileForm.id) {
      await updateRetrievalProfile(profileForm.id, payload)
      ElMessage.success('优化配置已更新')
    } else {
      await createRetrievalProfile(payload)
      ElMessage.success('优化配置已创建')
    }
    profileDialogVisible.value = false
    await loadRetrievalProfiles()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  }
}

async function handleDeleteProfile(item: RetrievalProfile) {
  if (item.is_builtin) {
    ElMessage.warning('内置配置不允许删除')
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除配置「${item.name}」？`, '提示', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await deleteRetrievalProfile(item.id)
    ElMessage.success('配置已删除')
    await loadRetrievalProfiles()
  } catch {
    // canceled
  }
}

async function setDefaultProfile(item: RetrievalProfile) {
  if (item.is_default) {
    return
  }
  try {
    await updateRetrievalProfile(item.id, { is_default: true })
    ElMessage.success('已设为默认配置')
    await loadRetrievalProfiles()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '设置默认失败')
  }
}

async function handleCreateUser() {
  if (!createUserForm.username || !createUserForm.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  try {
    await createUser(createUserForm)
    createUserForm.username = ''
    createUserForm.password = ''
    createUserForm.role = 'user'
    ElMessage.success('用户创建成功')
    await loadUsers()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '创建失败')
  }
}

async function toggleUserActive(userId: string, isActive: boolean) {
  try {
    await updateUser(userId, { is_active: isActive })
    ElMessage.success('状态已更新')
    await loadUsers()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '状态更新失败')
  }
}

async function toggleUserRole(userId: string, role: 'admin' | 'user') {
  try {
    await updateUser(userId, { role })
    ElMessage.success('角色已更新')
    await loadUsers()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '角色更新失败')
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadRetrievalProfiles()])
})
</script>
