<template>
  <div class="space-y-4">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <span>新增模型配置</span>
          <div class="flex gap-2">
            <el-button @click="validateCurrent">验证配置</el-button>
            <el-button type="primary" @click="create">保存</el-button>
          </div>
        </div>
      </template>

      <div class="grid gap-4 md:grid-cols-2">
        <el-input v-model="createForm.name" placeholder="配置名称" />
        <el-select v-model="createForm.provider_type" placeholder="Provider">
          <el-option label="OpenAI" value="openai" />
          <el-option label="Anthropic" value="anthropic" />
          <el-option label="Gemini" value="gemini" />
          <el-option label="OpenAI-Compatible" value="openai_compatible" />
        </el-select>
        <el-input v-model="createForm.endpoint_url" placeholder="端点 URL" />
        <el-input v-model="createForm.model_name" placeholder="模型名称" />
        <el-input v-model="createForm.api_key" show-password type="password" placeholder="API Key" />
        <el-switch v-model="createForm.is_default" active-text="设为默认" />
      </div>
    </el-card>

    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <span>已配置模型</span>
          <el-button text @click="loadProviders">刷新</el-button>
        </div>
      </template>

      <el-table :data="providers" stripe>
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="provider_type" label="类型" width="170" />
        <el-table-column prop="endpoint_url" label="端点" min-width="240" show-overflow-tooltip />
        <el-table-column prop="model_name" label="模型" width="180" />
        <el-table-column prop="api_key_masked" label="API Key" width="170" />
        <el-table-column label="默认" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button size="small" link @click="openEditDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" link @click="remove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editDialogVisible" title="编辑模型配置" width="720px">
      <div class="grid gap-4 md:grid-cols-2">
        <el-input v-model="editForm.name" placeholder="配置名称" />
        <el-select v-model="editForm.provider_type" placeholder="Provider">
          <el-option label="OpenAI" value="openai" />
          <el-option label="Anthropic" value="anthropic" />
          <el-option label="Gemini" value="gemini" />
          <el-option label="OpenAI-Compatible" value="openai_compatible" />
        </el-select>
        <el-input v-model="editForm.endpoint_url" placeholder="端点 URL" />
        <el-input v-model="editForm.model_name" placeholder="模型名称" />
        <el-input
          v-model="editForm.api_key"
          show-password
          type="password"
          placeholder="API Key（留空表示不修改）"
        />
        <el-switch v-model="editForm.is_default" active-text="设为默认" />
      </div>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button @click="validateEdit">验证配置</el-button>
        <el-button type="primary" @click="submitEdit">保存修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import {
  createProvider,
  deleteProvider,
  listProviders,
  updateProvider,
  validateModel,
} from '../api'
import type { ProviderConfig } from '../types'

const providers = ref<ProviderConfig[]>([])
const editDialogVisible = ref(false)
const editingId = ref('')

const createForm = reactive({
  name: '默认 OpenAI 配置',
  provider_type: 'openai',
  endpoint_url: 'https://api.openai.com',
  model_name: 'gpt-4o-mini',
  api_key: '',
  is_default: true,
  capabilities: {
    chat: true,
    embed: true,
    rerank: false,
  },
})

const editForm = reactive({
  name: '',
  provider_type: 'openai',
  endpoint_url: '',
  model_name: '',
  api_key: '',
  is_default: false,
  capabilities: {
    chat: true,
    embed: true,
    rerank: false,
  },
})

async function loadProviders() {
  providers.value = await listProviders()
}

async function create() {
  try {
    await createProvider(createForm)
    ElMessage.success('模型配置已保存')
    createForm.api_key = ''
    await loadProviders()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  }
}

async function validateCurrent() {
  try {
    const result = await validateModel({
      provider_type: createForm.provider_type,
      endpoint_url: createForm.endpoint_url,
      model_name: createForm.model_name,
      api_key: createForm.api_key,
    })
    if (result.valid) {
      ElMessage.success(`验证成功：${result.message}`)
    } else {
      ElMessage.warning(`验证失败：${result.message}`)
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '验证失败')
  }
}

function openEditDialog(row: ProviderConfig) {
  editingId.value = row.id
  editForm.name = row.name
  editForm.provider_type = row.provider_type
  editForm.endpoint_url = row.endpoint_url
  editForm.model_name = row.model_name
  editForm.api_key = ''
  editForm.is_default = row.is_default
  editForm.capabilities = {
    chat: true,
    embed: true,
    rerank: false,
    ...(row.capabilities || {}),
  }
  editDialogVisible.value = true
}

async function validateEdit() {
  if (!editForm.api_key) {
    ElMessage.warning('编辑校验需要填写 API Key')
    return
  }
  try {
    const result = await validateModel({
      provider_type: editForm.provider_type,
      endpoint_url: editForm.endpoint_url,
      model_name: editForm.model_name,
      api_key: editForm.api_key,
    })
    if (result.valid) {
      ElMessage.success(`验证成功：${result.message}`)
    } else {
      ElMessage.warning(`验证失败：${result.message}`)
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '验证失败')
  }
}

async function submitEdit() {
  if (!editingId.value) {
    return
  }
  try {
    const payload: Record<string, unknown> = {
      name: editForm.name,
      provider_type: editForm.provider_type,
      endpoint_url: editForm.endpoint_url,
      model_name: editForm.model_name,
      is_default: editForm.is_default,
      capabilities: editForm.capabilities,
    }
    if (editForm.api_key) {
      payload.api_key = editForm.api_key
    }

    await updateProvider(editingId.value, payload)
    ElMessage.success('模型配置已更新')
    editDialogVisible.value = false
    await loadProviders()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '更新失败')
  }
}

async function remove(id: string) {
  await deleteProvider(id)
  ElMessage.success('删除成功')
  await loadProviders()
}

onMounted(loadProviders)
</script>
