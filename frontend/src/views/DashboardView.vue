<template>
  <div class="space-y-4">
    <div class="grid gap-4 md:grid-cols-3">
      <el-card>
        <div class="text-sm text-slate-500">模型配置</div>
        <div class="mt-2 text-3xl font-semibold text-slate-800">{{ stats.providers }}</div>
      </el-card>
      <el-card>
        <div class="text-sm text-slate-500">知识库</div>
        <div class="mt-2 text-3xl font-semibold text-slate-800">{{ stats.libraries }}</div>
      </el-card>
      <el-card>
        <div class="text-sm text-slate-500">会话数</div>
        <div class="mt-2 text-3xl font-semibold text-slate-800">{{ stats.sessions }}</div>
      </el-card>
    </div>

    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <span>系统状态</span>
          <el-button text @click="loadData">刷新</el-button>
        </div>
      </template>
      <div class="space-y-2 text-sm text-slate-600">
        <div>默认语言：中文</div>
        <div>检索策略：混合检索 + 可选重排</div>
        <div>知识库归属：默认私有，管理员可标记共享</div>
        <div>API Key：后端密文存储，前端脱敏展示</div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'

import { listLibraries, listProviders, listSessions } from '../api'

const stats = reactive({
  providers: 0,
  libraries: 0,
  sessions: 0,
})

async function loadData() {
  try {
    const [providers, libraries, sessions] = await Promise.all([
      listProviders(),
      listLibraries(),
      listSessions(),
    ])
    stats.providers = providers.length
    stats.libraries = libraries.length
    stats.sessions = sessions.length
  } catch {
    ElMessage.warning('仪表盘数据加载失败，请检查后端服务')
  }
}

onMounted(loadData)
</script>
