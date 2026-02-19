<template>
  <div class="login-shell">
    <div class="login-panel">
      <div class="mb-6">
        <h1 class="text-2xl font-semibold">RAG 平台登录</h1>
        <p class="mt-2 text-sm text-slate-500">默认账号可使用 admin / admin123456</p>
      </div>

      <el-form :model="form" :rules="rules" ref="formRef" label-position="top" @submit.prevent>
        <el-form-item prop="username" label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item prop="password" label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-button type="primary" class="w-full" :loading="loading" @click="submit">登录</el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'

import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const loading = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  username: 'admin',
  password: 'admin123456',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }
  loading.value = true
  try {
    await auth.loginWithPassword(form)
    router.push('/')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at 20% 20%, rgba(14, 165, 233, 0.25), transparent 45%),
    radial-gradient(circle at 80% 80%, rgba(15, 23, 42, 0.4), transparent 55%),
    #f8fafc;
}

.login-panel {
  width: 420px;
  max-width: calc(100vw - 2rem);
  border-radius: 18px;
  background: white;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.18);
  padding: 2rem;
}
</style>
