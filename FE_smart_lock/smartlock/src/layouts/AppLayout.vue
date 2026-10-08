<script setup>
import { ref, computed, provide, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createDoorSession, doorSessionKey } from '../composables/useDoorSession'
import AppIcon from '../components/ui/AppIcon.vue'
import AppDialog from '../components/ui/AppDialog.vue'
import CommandStatus from '../components/CommandStatus.vue'
const route = useRoute(),
  router = useRouter()
const menuOpen = ref(false)
const acknowledgeOpen = ref(false)
const username = localStorage.getItem('username') || '用户'
const isAdmin = localStorage.getItem('role') === 'admin'
const session = createDoorSession()
provide(doorSessionKey, session)
const { command, commandStatus } = session
const navigation = computed(() => [
  { path: '/dashboard', name: '门控', icon: 'doors' },
  { path: '/dashboard/records', name: '记录', icon: 'records' },
  { path: '/dashboard/guests', name: '访客', icon: 'guests' },
  ...(isAdmin
    ? [
        { path: '/dashboard/alarms', name: '报警', icon: 'alarms' },
        { path: '/dashboard/users', name: '用户与权限', icon: 'users' }
      ]
    : [])
])
function logout() {
  for (const key of ['token', 'username', 'role']) localStorage.removeItem(key)
  router.replace('/')
}
onMounted(session.initialize)
function acknowledge() {
  commandStatus.value = 'acknowledged'
  acknowledgeOpen.value = false
  session.resetFlow()
}
</script>
<template>
  <a class="sr-only" href="#main-content">跳到主要内容</a>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-symbol"><AppIcon name="lock" :size="21" /></div>
        <div>
          <div class="brand-name">SmartLock</div>
          <div class="brand-caption">ACCESS MANAGEMENT</div>
        </div>
      </div>
      <p class="nav-label">工作空间</p>
      <nav aria-label="主要导航">
        <RouterLink
          v-for="item in navigation"
          :key="item.path"
          :to="item.path"
          :class="['nav-link', { 'router-link-active': route.path === item.path }]"
          :active-class="item.path === '/dashboard' ? '' : 'router-link-active'"
        >
          <AppIcon :name="item.icon" />
          {{ item.name }}
        </RouterLink>
      </nav>
      <div class="sidebar-footer">
        <AppIcon name="shield" :size="18" />
        <p style="margin-top: 8px">验证身份 · 确认执行</p>
        <p>SmartLock 控制台</p>
      </div>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div class="breadcrumb">
          <button class="icon-button mobile-menu" aria-label="打开导航" @click="menuOpen = true">
            <AppIcon name="menu" />
          </button>
          <span>工作空间</span>
          <span>/</span>
          <strong>{{ route.meta.title }}</strong>
        </div>
        <div class="topbar-actions">
          <RouterLink class="account-link" to="/dashboard/security">
            <span class="avatar">{{ username.slice(0, 1).toUpperCase() }}</span>
            <span class="account-name">{{ username }}</span>
          </RouterLink>
          <button class="icon-button" aria-label="退出登录" @click="logout">
            <AppIcon name="logout" :size="18" />
          </button>
        </div>
      </header>
      <main id="main-content" class="main-content" tabindex="-1">
        <RouterView />
        <section v-if="command" class="panel command-tray">
          <div class="panel-head">
            <div>
              <h3>本次{{ command.action }}结果</h3>
              <p class="subtext mono">{{ command.deviceId }}</p>
            </div>
            <RouterLink
              v-if="route.path !== '/dashboard'"
              class="button button--small"
              to="/dashboard"
            >
              返回门控
            </RouterLink>
          </div>
          <div class="panel-body">
            <CommandStatus :command-id="command.id" @settled="session.settled" />
            <p class="subtext">执行回执描述本次操作，设备状态以最近上报为准。</p>
            <button
              v-if="commandStatus === 'unknown'"
              class="table-action"
              @click="acknowledgeOpen = true"
            >
              已核查现场，结束本次跟踪
            </button>
          </div>
        </section>
      </main>
    </div>
  </div>
  <AppDialog v-if="menuOpen" title="工作空间" @close="menuOpen = false">
    <nav class="stack stack--small" aria-label="移动导航">
      <RouterLink
        v-for="item in navigation"
        :key="item.path"
        class="button"
        :to="item.path"
        @click="menuOpen = false"
      >
        <AppIcon :name="item.icon" />
        {{ item.name }}
      </RouterLink>
      <RouterLink class="button" to="/dashboard/security" @click="menuOpen = false">
        账户与安全
      </RouterLink>
    </nav>
  </AppDialog>
  <AppDialog
    v-if="acknowledgeOpen"
    title="结束结果待确认的操作跟踪"
    @close="acknowledgeOpen = false"
  >
    <div class="stack">
      <p>
        本次执行结果仍然未知。请确认已检查现场状态，再结束跟踪并进行新的操作。结束跟踪不会撤销或重新发送原命令。
      </p>
      <div class="button-group">
        <button class="button button--primary" @click="acknowledge">已核查，结束跟踪</button>
        <button class="button" @click="acknowledgeOpen = false">继续核查</button>
      </div>
    </div>
  </AppDialog>
</template>
