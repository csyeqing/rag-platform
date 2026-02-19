<template>
  <div class="min-h-screen bg-slate-100">
    <div class="flex min-h-screen">
      <aside class="hidden w-64 flex-col bg-slate-900 px-4 py-6 text-slate-100 lg:flex">
        <div class="mb-6 rounded-lg bg-slate-800 p-4">
          <div class="text-xs uppercase text-slate-400">RAG Web 平台</div>
          <div class="mt-2 text-lg font-semibold">MVP 控制台</div>
        </div>
        <nav class="flex flex-1 flex-col gap-2">
          <RouterLink
            v-for="item in menus"
            :key="item.path"
            :to="item.path"
            class="rounded-md px-3 py-2 text-sm transition"
            :class="{ 'bg-cyan-500 text-slate-900': isMenuActive(item.path) }"
          >
            {{ item.label }}
          </RouterLink>
        </nav>
        <div class="rounded-md border border-slate-700 p-3 text-xs text-slate-300">
          当前用户：{{ auth.username }}
          <br />
          角色：{{ auth.role }}
        </div>
      </aside>

      <main class="flex-1">
        <header class="sticky top-0 z-20 flex items-center justify-between border-b border-slate-200 bg-white/90 px-6 py-3 backdrop-blur">
          <div class="font-medium text-slate-700">{{ pageTitle }}</div>
          <div class="flex items-center gap-2">
            <el-tag type="info">{{ auth.role }}</el-tag>
            <el-button size="small" type="danger" plain @click="handleLogout">退出</el-button>
          </div>
        </header>
        <section class="p-6">
          <RouterView />
        </section>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const menus = [
  { path: '/', label: '仪表盘' },
  { path: '/providers', label: '模型配置' },
  { path: '/knowledge-base', label: '知识库管理' },
  { path: '/chat', label: 'AI 聊天' },
  { path: '/settings', label: '系统设置' },
]

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const pageTitle = computed(() => menus.find((item) => item.path === route.path)?.label || '控制台')

function isMenuActive(path: string) {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path === path || route.path.startsWith(path + '/')
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>
