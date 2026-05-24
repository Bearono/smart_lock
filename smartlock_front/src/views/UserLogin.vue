<template>
  <div class="min-h-screen flex items-center justify-center relative overflow-hidden bg-cover bg-center"
       style="background-image: url('https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop');">

    <div class="absolute inset-0 bg-gray-900 bg-opacity-60 backdrop-blur-sm"></div>

    <!-- 注册卡片（独立显示） -->
    <div v-if="isRegisterMode" class="relative z-10 w-full max-w-md p-8 bg-gray-800 bg-opacity-70 backdrop-filter backdrop-blur-xl rounded-2xl border border-gray-600 shadow-2xl">
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-indigo-600 mb-4 shadow-[0_0_15px_rgba(79,70,229,0.5)]">
          <i class="fas fa-user-plus text-2xl text-white"></i>
        </div>
        <h2 class="text-3xl font-bold text-white tracking-widest">管理员注册</h2>
        <p class="text-gray-300 text-xs mt-2 tracking-[0.2em] uppercase">创建新账号</p>
      </div>

      <form @submit.prevent="handleRegister" class="space-y-6">
        <div class="relative group">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <i class="fas fa-user text-gray-400 group-focus-within:text-indigo-400 transition-colors"></i>
          </div>
          <input
            v-model="regForm.username"
            type="text"
            placeholder="请输入用户名"
            class="w-full pl-10 pr-4 py-3 bg-gray-900 bg-opacity-80 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            required
          >
        </div>

        <div class="relative group">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <i class="fas fa-envelope text-gray-400 group-focus-within:text-indigo-400 transition-colors"></i>
          </div>
          <input
            v-model="regForm.email"
            type="email"
            placeholder="请输入邮箱地址（用于接收动态码）"
            class="w-full pl-10 pr-4 py-3 bg-gray-900 bg-opacity-80 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            required
          >
        </div>

        <div class="relative group">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <i class="fas fa-lock text-gray-400 group-focus-within:text-indigo-400 transition-colors"></i>
          </div>
          <input
            v-model="regForm.password"
            type="password"
            placeholder="请输入密码"
            class="w-full pl-10 pr-4 py-3 bg-gray-900 bg-opacity-80 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            required
          >
        </div>

        <div class="relative group">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <i class="fas fa-check-circle text-gray-400 group-focus-within:text-indigo-400 transition-colors"></i>
          </div>
          <input
            v-model="regForm.confirmPassword"
            type="password"
            placeholder="请再次确认密码"
            class="w-full pl-10 pr-4 py-3 bg-gray-900 bg-opacity-80 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            required
          >
        </div>

        <div v-if="errorMsg" class="text-red-400 text-sm text-center bg-red-900/20 py-1 rounded border border-red-500/20">
          <i class="fas fa-exclamation-triangle mr-1"></i> {{ errorMsg }}
        </div>

        <button
          type="submit"
          :disabled="isLoading"
          class="w-full py-3 px-4 rounded-lg shadow-lg text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 focus:outline-none transform hover:scale-[1.02] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed mt-4"
        >
          <span v-if="isLoading"><i class="fas fa-circle-notch fa-spin mr-2"></i>注册中...</span>
          <span v-else>创建管理员账号</span>
        </button>
      </form>

      <div class="mt-6 text-center">
        <p class="text-sm text-gray-400">
          已有账号?
          <span @click="isRegisterMode = false; errorMsg = ''" class="text-indigo-400 hover:text-indigo-300 font-medium cursor-pointer ml-1 hover:underline transition select-none">
            直接登录
          </span>
        </p>
      </div>
    </div>

    <!-- 登录卡片 -->
    <div v-else class="relative z-10 w-full max-w-md p-8 bg-gray-800 bg-opacity-70 backdrop-filter backdrop-blur-xl rounded-2xl border border-gray-600 shadow-2xl transition-all duration-500"
         :class="stepClass">

      <div class="text-center mb-6">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-indigo-600 mb-4 shadow-[0_0_15px_rgba(79,70,229,0.5)]">
          <i class="fas fa-shield-alt text-2xl text-white"></i>
        </div>
        <h2 class="text-3xl font-bold text-white tracking-widest">SECURE<span class="text-indigo-400">VISION</span></h2>
        <p class="text-gray-300 text-xs mt-2 tracking-[0.2em] uppercase">{{ stepLabel }}</p>
      </div>

      <!-- 步骤指示器 -->
      <div v-if="step > 0" class="flex items-center justify-center gap-2 mb-6">
        <div class="step-dot" :class="{ active: step >= 1, done: step > 1 }">1</div>
        <div class="step-line" :class="{ active: step >= 2 }"></div>
        <div class="step-dot" :class="{ active: step >= 2 }">2</div>
      </div>

      <!-- 步骤0：账号 + 邮箱 -->
      <form v-if="step === 0" @submit.prevent="handlePreLogin" class="space-y-6">
        <div class="relative group">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <i class="fas fa-user text-gray-400 group-focus-within:text-indigo-400 transition-colors"></i>
          </div>
          <input
            v-model="form.username"
            type="text"
            placeholder="请输入用户名"
            class="w-full pl-10 pr-4 py-3 bg-gray-900 bg-opacity-80 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            required
          >
        </div>

        <div class="relative group">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <i class="fas fa-envelope text-gray-400 group-focus-within:text-indigo-400 transition-colors"></i>
          </div>
          <input
            v-model="form.email"
            type="email"
            placeholder="请输入邮箱地址"
            class="w-full pl-10 pr-4 py-3 bg-gray-900 bg-opacity-80 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            required
          >
        </div>

        <div class="relative group">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <i class="fas fa-lock text-gray-400 group-focus-within:text-indigo-400 transition-colors"></i>
          </div>
          <input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            class="w-full pl-10 pr-4 py-3 bg-gray-900 bg-opacity-80 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
            required
          >
        </div>

        <div v-if="errorMsg" class="text-red-400 text-sm text-center bg-red-900/20 py-1 rounded border border-red-500/20">
          <i class="fas fa-exclamation-triangle mr-1"></i> {{ errorMsg }}
        </div>

        <button
          type="submit"
          :disabled="isLoading"
          class="w-full py-3 px-4 rounded-lg shadow-lg text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 focus:outline-none transform hover:scale-[1.02] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed mt-4"
        >
          <span v-if="isLoading"><i class="fas fa-circle-notch fa-spin mr-2"></i>发送中...</span>
          <span v-else>获取动态验证码</span>
        </button>

        <div class="mt-6 text-center">
          <p class="text-sm text-gray-400">
            还没有账号?
            <span @click="isRegisterMode = true; errorMsg = ''" class="text-indigo-400 hover:text-indigo-300 font-medium cursor-pointer ml-1 hover:underline transition select-none">
              立即注册
            </span>
          </p>
        </div>
      </form>

      <!-- 步骤1：输入邮箱收到的动态码 -->
      <form v-else-if="step === 1" @submit.prevent="handleMfaVerify" class="space-y-5">
        <div class="text-center mb-4">
          <i class="fas fa-envelope-open-text text-4xl text-indigo-400 mb-2 block"></i>
          <p class="text-gray-300 text-sm">动态码已发送到</p>
          <p class="text-indigo-400 font-bold text-base truncate max-w-full">{{ form.email }}</p>
        </div>

        <div class="relative group">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <i class="fas fa-key text-gray-400 group-focus-within:text-indigo-400 transition-colors"></i>
          </div>
          <input
            v-model="form.otpCode"
            type="text"
            maxlength="6"
            placeholder="请输入6位动态码"
            class="w-full pl-10 pr-4 py-3 bg-gray-900 bg-opacity-80 border border-gray-600 rounded-lg text-white text-center text-xl tracking-[0.25em] font-bold focus:outline-none focus:border-indigo-500 transition-all"
            required
          >
        </div>

        <div v-if="errorMsg" class="text-red-400 text-sm text-center bg-red-900/20 py-1 rounded border border-red-500/20">
          <i class="fas fa-exclamation-triangle mr-1"></i> {{ errorMsg }}
        </div>

        <button
          type="submit"
          :disabled="isLoading || form.otpCode.length !== 6"
          class="w-full py-3 px-4 rounded-lg shadow-lg text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 focus:outline-none transform hover:scale-[1.02] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed mt-4"
        >
          <span v-if="isLoading"><i class="fas fa-circle-notch fa-spin mr-2"></i>验证中...</span>
          <span v-else>确认验证</span>
        </button>

        <div class="text-center">
          <button type="button" @click="step = 0; errorMsg = ''; form.otpCode = ''" class="text-gray-400 hover:text-gray-300 text-sm">
            <i class="fas fa-arrow-left mr-1"></i>重新输入账号
          </button>
        </div>
      </form>

    </div>
  </div>
</template>

<script>
import { auth } from '../api/index'

export default {
  name: 'UserLogin',
  data() {
    return {
      isRegisterMode: false,
      isLoading: false,
      errorMsg: '',
      step: 0,
      form: {
        username: '',
        email: '',
        password: '',
        otpCode: ''
      },
      regForm: {
        username: '',
        email: '',
        password: '',
        confirmPassword: ''
      },
      preToken: ''
    };
  },
  computed: {
    stepLabel() {
      if (this.step === 0) return '智能安防控制终端'
      if (this.step === 1) return '邮箱动态验证'
      return ''
    },
    stepClass() {
      if (this.step === 1) return 'h-[540px]'
      return 'h-[560px]'
    }
  },
  methods: {
    async handlePreLogin() {
      this.errorMsg = ''
      if (!this.form.username || !this.form.password || !this.form.email) {
        this.errorMsg = '请输入用户名、邮箱和密码'
        return
      }
      this.isLoading = true
      try {
        const res = await auth.prelogin(this.form.username, this.form.email, this.form.password)
        this.preToken = res.data.pre_token
        this.step = 1
      } catch (error) {
        this.errorMsg = error?.response?.data?.msg || '账号、邮箱或密码错误'
      } finally {
        this.isLoading = false
      }
    },
    async handleMfaVerify() {
      if (this.form.otpCode.length !== 6) {
        this.errorMsg = '请输入6位验证码'
        return
      }
      this.isLoading = true
      this.errorMsg = ''
      try {
        const res = await auth.verifyMfa(this.preToken, this.form.otpCode)
        localStorage.setItem('token', res.data.access_token)
        localStorage.setItem('username', this.form.username)
        this.$router.push('/dashboard')
      } catch (error) {
        this.errorMsg = error?.response?.data?.msg || '验证码错误'
        this.form.otpCode = ''
      } finally {
        this.isLoading = false
      }
    },
    async handleRegister() {
      this.errorMsg = ''
      if (!this.regForm.username || !this.regForm.password) {
        this.errorMsg = '请输入账号和密码'
        return
      }
      if (!this.regForm.email) {
        this.errorMsg = '请输入邮箱地址'
        return
      }
      if (this.regForm.password !== this.regForm.confirmPassword) {
        this.errorMsg = '两次输入的密码不一致'
        return
      }
      this.isLoading = true
      try {
        await auth.register(this.regForm.username, this.regForm.password, this.regForm.email)
        this.isRegisterMode = false
        this.form.username = this.regForm.username
        this.form.email = this.regForm.email
        this.regForm = { username: '', email: '', password: '', confirmPassword: '' }
        alert('注册成功，请登录')
      } catch (error) {
        this.errorMsg = error?.response?.data?.msg || '注册失败'
      } finally {
        this.isLoading = false
      }
    }
  }
};
</script>

<style scoped>
.step-dot {
  width: 28px; height: 28px; border-radius: 50%;
  border: 2px solid #4b5563;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; color: #6b7280; background: #1f2937;
  transition: all 0.3s;
}
.step-dot.active { border-color: #6366f1; color: #6366f1; }
.step-dot.done { border-color: #10b981; background: #10b981; color: white; }
.step-line { width: 40px; height: 2px; background: #4b5563; transition: background 0.3s; }
.step-line.active { background: #6366f1; }
</style>