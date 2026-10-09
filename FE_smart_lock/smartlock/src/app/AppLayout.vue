<script setup lang="ts">
import { ref, provide, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createDoorSession, doorSessionKey } from '../features/door/useDoorSession.ts'
import AppIcon from '../shared/ui/AppIcon.vue'
import AppDialog from '../shared/ui/AppDialog.vue'
import CommandStatus from '../features/door/CommandStatus.vue'
const route = useRoute(),
  router = useRouter()
const acknowledgeOpen = ref(false)
const username = localStorage.getItem('username') || '用户'
const isAdmin = localStorage.getItem('role') === 'admin'
const session = createDoorSession()
provide(doorSessionKey, session)
const { command, commandStatus } = session
const navigation = [
  { path: '/dashboard', name: '我的家', icon: 'doors' },
  { path: '/dashboard/records', name: '动态', icon: 'records' },
  { path: '/dashboard/guests', name: '访客', icon: 'guests' },
  { path: '/dashboard/security', name: '设置', icon: 'shield' }
]
const pageTitle = computed(
  () =>
    ({
      '/dashboard': '我的家',
      '/dashboard/records': '家门动态',
      '/dashboard/guests': '访客通行',
      '/dashboard/security': '账户与设置',
      '/dashboard/alarms': '异常提醒',
      '/dashboard/users': '成员与权限',
      '/dashboard/evidence': '安全证据'
    })[route.path] || '我的家'
)

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
    <aside class="home-sidebar">
      <RouterLink to="/dashboard" class="brand">
        <span class="brand-symbol"><AppIcon name="doors" :size="24" /></span>
        <span>
          <strong class="brand-name">SmartLock</strong>
          <span class="brand-caption">让每次回家，都安心</span>
        </span>
      </RouterLink>
      <div class="home-space">
        <AppIcon name="home" :size="19" />
        <div>
          <strong>我的家庭</strong>
          <span>门锁与摄像头</span>
        </div>
      </div>
      <p class="navigation-label">日常使用</p>
      <nav class="home-navigation" aria-label="主要导航">
        <RouterLink
          v-for="item in navigation"
          :key="item.path"
          :to="item.path"
          :class="['nav-link', { 'router-link-active': route.path === item.path }]"
          :active-class="item.path === '/dashboard' ? '' : 'router-link-active'"
          :aria-current="route.path === item.path ? 'page' : undefined"
        >
          <AppIcon :name="item.icon" />
          {{ item.name }}
          <span class="nav-indicator" />
        </RouterLink>
      </nav>
      <nav v-if="isAdmin" class="management-navigation" aria-label="家庭管理">
        <span class="navigation-label">家庭管理</span>
        <RouterLink to="/dashboard/alarms">
          <AppIcon name="alarms" :size="19" />
          异常提醒
        </RouterLink>
        <RouterLink to="/dashboard/users">
          <AppIcon name="users" :size="19" />
          成员与权限
        </RouterLink>
        <RouterLink to="/dashboard/evidence">
          <AppIcon name="shield" :size="19" />
          安全证据
        </RouterLink>
      </nav>
      <div class="sidebar-note">
        <AppIcon name="shield" :size="24" />
        <strong>家的隐私，认真守护</strong>
        <p>画面与设备控制仅向授权账户开放。</p>
      </div>
    </aside>
    <div class="workspace">
      <header class="home-header">
        <div class="workspace-heading">
          <span>家庭空间</span>
          <AppIcon name="chevron" :size="14" />
          <strong>{{ pageTitle }}</strong>
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
              返回我的家
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
