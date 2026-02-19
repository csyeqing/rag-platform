<template>
  <div class="space-y-4">
    <el-card>
      <template #header>
        <span>系统设置（MVP）</span>
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
            <el-button
              size="small"
              link
              @click="toggleUserActive(row.id, !row.is_active)"
            >
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { createUser, listUsers, updateUser } from '../api'
import { useAuthStore } from '../stores/auth'
import type { UserListItem } from '../types'

const auth = useAuthStore()

const settings = reactive({
  language: localStorage.getItem('rag_setting_language') || 'zh-CN',
  defaultShowCitations: localStorage.getItem('rag_setting_show_citations') !== '0',
  defaultTopK: Number(localStorage.getItem('rag_setting_top_k') || '5'),
})

const users = ref<UserListItem[]>([])
const createUserForm = reactive({
  username: '',
  password: '',
  role: 'user',
})

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

onMounted(loadUsers)
</script>
