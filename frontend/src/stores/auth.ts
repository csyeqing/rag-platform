import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'

import { getCurrentUser, login } from '../api'
import type { UserMe, UserRole } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('rag_token') || '')
  const username = ref(localStorage.getItem('rag_username') || '')
  const role = ref<UserRole>((localStorage.getItem('rag_role') as UserRole) || 'user')
  const user = ref<UserMe | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  // 监听 token 变化，同步到 localStorage
  watch(token, (newToken) => {
    if (newToken) {
      localStorage.setItem('rag_token', newToken)
    } else {
      localStorage.removeItem('rag_token')
    }
  })

  async function loginWithPassword(payload: { username: string; password: string }) {
    const result = await login(payload.username, payload.password)
    token.value = result.token.access_token
    username.value = result.username
    role.value = result.role
    localStorage.setItem('rag_token', token.value)
    localStorage.setItem('rag_username', username.value)
    localStorage.setItem('rag_role', role.value)
    await fetchMe()
  }

  async function fetchMe() {
    if (!token.value) {
      user.value = null
      return
    }
    try {
      user.value = await getCurrentUser()
    } catch (error: any) {
      // 如果是 401，说明 token 无效，清除状态
      if (error.response?.status === 401) {
        logout()
      }
      throw error
    }
  }

  function logout() {
    token.value = ''
    username.value = ''
    role.value = 'user'
    user.value = null
    localStorage.removeItem('rag_token')
    localStorage.removeItem('rag_username')
    localStorage.removeItem('rag_role')
  }

  return {
    token,
    username,
    role,
    user,
    isAuthenticated,
    loginWithPassword,
    fetchMe,
    logout,
  }
})
