<template>
  <div class="space-y-4">
    <el-card>
      <template #header>
        <div class="flex items-center justify-between">
          <span>知识库列表</span>
          <el-button type="primary" size="small" @click="createDialogVisible = true">新增知识库</el-button>
        </div>
      </template>
      <el-table :data="libraries" stripe>
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="类型" width="140">
          <template #default="{ row }">{{ libraryTypeLabel(row.library_type) }}</template>
        </el-table-column>
        <el-table-column prop="owner_type" label="归属" width="120" />
        <el-table-column prop="root_path" label="目录" min-width="260" show-overflow-tooltip />
        <el-table-column label="标签" min-width="220">
          <template #default="{ row }">
            <div class="flex flex-wrap gap-1">
              <el-tag v-for="tag in row.tags" :key="tag" size="small">{{ tag }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="380">
          <template #default="{ row }">
            <el-button size="small" link :loading="editingLibraryId === row.id" @click="openEditDialog(row)">编辑</el-button>
            <el-button size="small" link @click="openFilesDialog(row)">查看文件</el-button>
            <el-button size="small" link @click="openGraphDialog(row)">查看知识图谱</el-button>
            <el-button size="small" link @click="openAddFileDialog(row)">新增文件</el-button>
            <el-button size="small" type="danger" link :loading="deletingLibraryId === row.id" @click="removeLibrary(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="lastTask">
      <template #header><span>最近任务状态</span></template>
      <div class="space-y-1 text-sm">
        <div>任务 ID: {{ lastTask.id }}</div>
        <div>类型: {{ lastTask.task_type }}</div>
        <div>状态: {{ lastTask.status }}</div>
        <div>详情: {{ JSON.stringify(lastTask.detail) }}</div>
      </div>
    </el-card>

    <el-dialog v-model="editDialogVisible" title="编辑知识库" width="600px">
      <div class="grid gap-3">
        <el-input v-model="editForm.name" placeholder="知识库名称" />
        <el-select v-model="editForm.library_type">
          <el-option
            v-for="item in libraryTypeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="editForm.owner_type" :disabled="auth.role !== 'admin'">
          <el-option label="私有" value="private" />
          <el-option label="共享" value="shared" />
        </el-select>
        <el-input v-model="editForm.description" placeholder="描述" />
        <el-input v-model="editTagsText" placeholder="标签，逗号分隔" />
      </div>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editingLibraryId !== ''" @click="submitEdit">{{ editingLibraryId !== '' ? '保存中...' : '保存' }}</el-button>
      </template>
    </el-dialog>

    <!-- 文件列表弹窗 -->
    <el-dialog v-model="filesDialogVisible" :title="`文件列表 - ${selectedLibraryName}`" width="80%">
      <div class="mb-4 flex items-center justify-between">
        <span></span>
        <el-button size="small" :loading="rebuildingIndex" :disabled="!selectedLibraryId || files.length === 0" @click="triggerRebuild">
          {{ rebuildingIndex ? '重建中...' : '重建索引' }}
        </el-button>
      </div>
      <el-table :data="files" stripe>
        <el-table-column prop="filename" label="文件名" min-width="180" />
        <el-table-column prop="file_type" label="类型" width="100" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="filepath" label="路径" min-width="260" show-overflow-tooltip />
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button size="small" type="danger" link :loading="deletingFileId === row.id" @click="removeFile(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 知识图谱弹窗 -->
    <el-dialog v-model="graphDialogVisible" :title="`知识图谱 - ${selectedLibraryName}`" width="80%">
      <div class="mb-4 flex items-center justify-between">
        <div class="rounded bg-purple-50 p-2 text-xs text-purple-700">
          💡 知识图谱用于从文档中提取实体（如人名、机构、术语）和关系。需先有内容并重建索引后才能生成图谱。
        </div>
        <div class="flex gap-2">
          <el-button :loading="graphLoading" :disabled="!selectedLibraryId" @click="selectedLibraryId ? loadGraph(selectedLibraryId) : null">
            刷新图谱
          </el-button>
          <el-button type="primary" :loading="rebuildingGraph" :disabled="!selectedLibraryId" @click="triggerGraphRebuild">
            {{ rebuildingGraph ? '重建中...' : '重建图谱' }}
          </el-button>
        </div>
      </div>

      <div v-if="graph" class="space-y-4">
        <div class="grid gap-3 md:grid-cols-3">
          <el-statistic title="图谱节点数" :value="graph.node_count" />
          <el-statistic title="图谱关系数" :value="graph.edge_count" />
          <el-statistic title="展示节点" :value="graph.nodes.length" />
        </div>
        <el-tabs type="border-card">
          <el-tab-pane label="实体节点">
            <el-table :data="graph.nodes" stripe max-height="400">
              <el-table-column prop="display_name" label="实体" min-width="180" />
              <el-table-column prop="entity_type" label="类型" width="120" />
              <el-table-column prop="frequency" label="频次" width="100" />
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="实体关系">
            <el-table :data="graph.edges" stripe max-height="400">
              <el-table-column prop="source_entity" label="源实体" min-width="150" />
              <el-table-column prop="relation_type" label="关系类型" width="130" />
              <el-table-column prop="target_entity" label="目标实体" min-width="150" />
              <el-table-column prop="weight" label="权重" width="90" />
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </div>
      <div v-else class="text-sm text-slate-500">该知识库暂无图谱数据，先上传文档并构建索引。</div>
    </el-dialog>

    <!-- 创建知识库弹窗 -->
    <el-dialog v-model="createDialogVisible" title="创建知识库" width="600px">
      <div class="grid gap-4">
        <el-input v-model="createForm.name" placeholder="例如：产品文档、客服知识库" />
        <el-select v-model="createForm.library_type" style="width: 100%">
          <el-option
            v-for="item in libraryTypeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="createForm.owner_type" style="width: 100%">
          <el-option label="私有（仅自己可用）" value="private" />
          <el-option v-if="auth.role === 'admin'" label="共享（所有用户可用，管理员创建）" value="shared" />
        </el-select>
        <el-input v-model="createForm.description" placeholder="简要描述这个知识库的用途" />
        <el-input v-model="createForm.root_path" placeholder="本地同步目录路径，不填则使用默认" />
        <el-input v-model="createTagsText" placeholder="用于分类和检索，例如：product,faq,policy" />
      </div>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingLibrary" @click="create">{{ creatingLibrary ? '创建中...' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <!-- 新增文件弹窗 -->
    <el-dialog v-model="addFileDialogVisible" :title="`新增文件 - ${selectedLibraryName}`" width="600px">
      <!-- 操作流程说明 -->
      <div class="mb-4 rounded bg-blue-50 p-3 text-sm text-blue-700">
        <div class="font-medium">📋 使用流程：</div>
        <div class="mt-1">1. 选择添加方式 → 2. 上传或同步 → 3. AI 即可检索</div>
        <div class="mt-1 text-xs">提示：上传文件会自动索引；如手动修改了文件内容，请点击“重建索引”</div>
      </div>

      <!-- 选择添加方式 -->
      <div class="mb-3">
        <el-radio-group v-model="addMethod">
          <el-radio value="sync">同步目录</el-radio>
          <el-radio value="upload">上传文件</el-radio>
        </el-radio-group>
      </div>

      <!-- 根据选择显示不同内容 -->
      <div class="flex flex-col gap-3">
        <!-- 同步目录模式 -->
        <template v-if="addMethod === 'sync'">
          <div class="flex items-center gap-2">
            <el-input v-model="syncPath" placeholder="本地目录路径（如 ./data/docs）" :disabled="syncing" />
            <el-button :loading="syncing" :disabled="!selectedLibraryId || !syncPath" @click="triggerSync">{{ syncing ? '同步中...' : '开始同步' }}</el-button>
          </div>
          <el-tag v-if="syncResult" :type="syncResult.success ? 'success' : 'danger'">{{ syncResult.message }}</el-tag>
        </template>

        <!-- 上传文件模式 -->
        <template v-else>
          <div class="flex items-center gap-2">
            <input type="file" accept=".txt,.md,.csv" @change="onFileChange" />
          </div>
          <div class="flex items-center gap-2 mt-2">
             <el-tag v-if="selectedFile" type="info">{{ selectedFile.name }}</el-tag>
             <el-button type="primary" :loading="uploading" :disabled="!selectedFile" @click="uploadCurrentFile">
              {{ uploading ? '上传中...' : '上传并索引' }}
            </el-button>
          </div>
          <div class="mt-2 text-xs text-slate-500">支持 .txt, .md, .csv</div>
          <el-progress
              v-if="uploadProgress > 0 && uploadProgress < 100"
              :percentage="uploadProgress"
              :stroke-width="6"
              style="width: 100%"
            />
          <el-tag v-if="uploadResult" :type="uploadResult.success ? 'success' : 'danger'" class="mt-2">
              {{ uploadResult.message }}
          </el-tag>
        </template>
      </div>
      <div class="mt-2 text-right">
        <span class="text-xs text-green-600">上传后自动索引</span>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  createLibrary,
  deleteLibrary,
  deleteLibraryFile,
  getLibraryGraph,
  listLibraries,
  listLibraryFiles,
  rebuildLibraryGraph,
  rebuildIndex,
  syncDirectory,
  updateLibrary,
  uploadFile,
} from '../api'
import { useAuthStore } from '../stores/auth'
import type { KnowledgeFile, KnowledgeGraphSnapshot, KnowledgeLibrary } from '../types'

const auth = useAuthStore()

const libraries = ref<KnowledgeLibrary[]>([])
const files = ref<KnowledgeFile[]>([])
const selectedLibraryId = ref('')
const syncPath = ref('')
const selectedFile = ref<File | null>(null)
const addMethod = ref<'sync' | 'upload'>('upload')
const lastTask = ref<Record<string, unknown> | null>(null)
const editDialogVisible = ref(false)
const filesDialogVisible = ref(false)
const graphDialogVisible = ref(false)
const createDialogVisible = ref(false)
const addFileDialogVisible = ref(false)
const graph = ref<KnowledgeGraphSnapshot | null>(null)
const graphLoading = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadResult = ref<{ success: boolean; message: string } | null>(null)
const deletingFileId = ref('')
const creatingLibrary = ref(false)
const syncing = ref(false)
const rebuildingIndex = ref(false)
const editingLibraryId = ref('')
const deletingLibraryId = ref('')
const rebuildingGraph = ref(false)
const syncResult = ref<{ success: boolean; message: string } | null>(null)
const rebuildResult = ref<{ success: boolean; message: string } | null>(null)
const libraryTypeOptions = [
  { value: 'general', label: '通用文档' },
  { value: 'novel_story', label: '小说/故事' },
  { value: 'enterprise_docs', label: '公司资料' },
  { value: 'scientific_paper', label: '科学论文' },
  { value: 'humanities_paper', label: '文科论文' },
]

const createForm = reactive({
  name: '我的知识库',
  library_type: 'general',
  owner_type: 'private',
  description: '文本类知识集合',
  root_path: '',
})
const createTagsText = ref('default')

const editForm = reactive({
  id: '',
  name: '',
  library_type: 'general',
  owner_type: 'private',
  description: '',
})
const editTagsText = ref('')

const selectedLibraryName = computed(() => {
  const found = libraries.value.find((item) => item.id === selectedLibraryId.value)
  return found?.name || ''
})

function tagsFromText(text: string): string[] {
  return text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function libraryTypeLabel(value: KnowledgeLibrary['library_type']) {
  const matched = libraryTypeOptions.find((item) => item.value === value)
  return matched?.label || value
}

async function loadLibraries() {
  libraries.value = await listLibraries()
  if (!selectedLibraryId.value && libraries.value.length > 0) {
    selectedLibraryId.value = libraries.value[0]?.id ?? ''
  }
  if (selectedLibraryId.value) {
    // 初始加载时不自动展开弹窗，但可以预加载数据（可选），这里仅加载文件列表，不强制加载图谱以节省资源
    // await Promise.all([loadFiles(selectedLibraryId.value)])
  }
}

async function loadFiles(libraryId: string) {
  files.value = await listLibraryFiles(libraryId)
}

async function loadGraph(libraryId: string) {
  graphLoading.value = true
  try {
    graph.value = await getLibraryGraph(libraryId, { limit_nodes: 50, limit_edges: 80 })
  } finally {
    graphLoading.value = false
  }
}

async function create() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  creatingLibrary.value = true
  try {
    await createLibrary({
      ...createForm,
      tags: tagsFromText(createTagsText.value),
    })
    ElMessage.success('知识库创建成功')
    createDialogVisible.value = false
    await loadLibraries()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '创建失败')
  } finally {
    creatingLibrary.value = false
  }
}

async function triggerSync() {
  if (!selectedLibraryId.value || !syncPath.value) {
    ElMessage.warning('请选择知识库并填写目录')
    return
  }
  syncing.value = true
  syncResult.value = null
  try {
    lastTask.value = await syncDirectory({
      library_id: selectedLibraryId.value,
      directory_path: syncPath.value,
      recursive: true,
    })
    syncResult.value = { success: true, message: '同步任务已触发' }
    ElMessage.success('目录同步任务已触发')
    // 如果当前打开了文件列表，刷新一下
    if (filesDialogVisible.value) {
        await loadFiles(selectedLibraryId.value)
    }
    setTimeout(() => {
      syncResult.value = null
    }, 3000)
  } catch (error: any) {
    syncResult.value = { success: false, message: error?.response?.data?.detail || '同步失败' }
    ElMessage.error(error?.response?.data?.detail || '同步失败')
  } finally {
    syncing.value = false
  }
}

async function triggerRebuild() {
  if (!selectedLibraryId.value) {
    ElMessage.warning('请先选择知识库')
    return
  }
  rebuildingIndex.value = true
  rebuildResult.value = null
  try {
    lastTask.value = await rebuildIndex({ library_id: selectedLibraryId.value })
    rebuildResult.value = { success: true, message: '索引重建任务已触发' }
    ElMessage.success('索引重建任务已触发')
    // 如果打开了图谱，刷新图谱
    if (graphDialogVisible.value) {
        await loadGraph(selectedLibraryId.value)
    }
    setTimeout(() => {
      rebuildResult.value = null
    }, 3000)
  } catch (error: any) {
    rebuildResult.value = { success: false, message: error?.response?.data?.detail || '重建失败' }
    ElMessage.error(error?.response?.data?.detail || '重建失败')
  } finally {
    rebuildingIndex.value = false
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] || null
}

async function uploadCurrentFile() {
  if (!selectedLibraryId.value || !selectedFile.value) {
    ElMessage.warning('请选择知识库并选择文件')
    return
  }
  uploading.value = true
  uploadProgress.value = 0
  uploadResult.value = null
  try {
    await uploadFile(selectedLibraryId.value, selectedFile.value, (percent) => {
      uploadProgress.value = percent
    })
    uploadResult.value = { success: true, message: '上传成功' }
    ElMessage.success('文件上传并索引完成')
    selectedFile.value = null // 清空文件选择
    // 如果当前打开了文件列表，刷新一下
    if (filesDialogVisible.value) {
        await loadFiles(selectedLibraryId.value)
    }
    // 3秒后清除结果提示
    setTimeout(() => {
      uploadResult.value = null
      uploadProgress.value = 0
    }, 3000)
  } catch (error: any) {
    uploadResult.value = { success: false, message: error?.response?.data?.detail || '上传失败' }
    ElMessage.error(error?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function openFilesDialog(row: KnowledgeLibrary) {
  selectedLibraryId.value = row.id
  filesDialogVisible.value = true
  await loadFiles(row.id)
}

async function openGraphDialog(row: KnowledgeLibrary) {
  selectedLibraryId.value = row.id
  graphDialogVisible.value = true
  await loadGraph(row.id)
}

function openAddFileDialog(row: KnowledgeLibrary) {
  selectedLibraryId.value = row.id
  addFileDialogVisible.value = true
  // Reset state
  addMethod.value = 'upload'
  syncPath.value = ''
  selectedFile.value = null
  uploadResult.value = null
  uploadProgress.value = 0
}

function openEditDialog(row: KnowledgeLibrary) {
  editForm.id = row.id
  editForm.name = row.name
  editForm.library_type = row.library_type || 'general'
  editForm.owner_type = row.owner_type
  editForm.description = row.description || ''
  editTagsText.value = row.tags.join(',')
  editDialogVisible.value = true
}

async function submitEdit() {
  if (!editForm.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  editingLibraryId.value = editForm.id
  try {
    await updateLibrary(editForm.id, {
      name: editForm.name,
      library_type: editForm.library_type,
      owner_type: editForm.owner_type,
      description: editForm.description,
      tags: tagsFromText(editTagsText.value),
    })
    editDialogVisible.value = false
    ElMessage.success('知识库更新成功')
    await loadLibraries()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '更新失败')
  } finally {
    editingLibraryId.value = ''
  }
}

async function removeLibrary(id: string) {
  try {
    await ElMessageBox.confirm('删除知识库会移除其索引和文件记录，是否继续？', '删除确认', {
      type: 'warning',
    })
    deletingLibraryId.value = id
    await deleteLibrary(id)
    ElMessage.success('知识库已删除')
    if (selectedLibraryId.value === id) {
      selectedLibraryId.value = ''
      files.value = []
      graph.value = null
      filesDialogVisible.value = false
      graphDialogVisible.value = false
    }
    await loadLibraries()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '删除失败')
    }
  } finally {
    deletingLibraryId.value = ''
  }
}

async function removeFile(fileId: string) {
  try {
    await ElMessageBox.confirm('确认删除该文件索引记录？', '删除确认', {
      type: 'warning',
    })
    deletingFileId.value = fileId
    await deleteLibraryFile(fileId)
    ElMessage.success('文件已删除')
    if (selectedLibraryId.value) {
      await loadFiles(selectedLibraryId.value)
      // 如果图谱也打开了，可能需要刷新，但通常不强制
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '删除失败')
    }
  } finally {
    deletingFileId.value = ''
  }
}

async function triggerGraphRebuild() {
  if (!selectedLibraryId.value) {
    ElMessage.warning('请先选择知识库')
    return
  }
  rebuildingGraph.value = true
  try {
    const result = await rebuildLibraryGraph(selectedLibraryId.value)
    ElMessage.success(
      `${result.message}（节点 ${result.node_count}，关系 ${result.edge_count}，chunk ${result.chunk_count}）`,
    )
    await loadGraph(selectedLibraryId.value)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '图谱重建失败')
  } finally {
    rebuildingGraph.value = false
  }
}

onMounted(loadLibraries)
</script>
