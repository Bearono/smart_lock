import { createRouter, createWebHistory } from 'vue-router'
const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/',
      name: 'UserLogin',
      component: () => import('../features/auth/LoginView.vue'),
      meta: { title: '登录' }
    },
    {
      path: '/guest',
      name: 'GuestVerify',
      component: () => import('../features/guests/GuestVerify.vue'),
      meta: { title: '访客通行' }
    },
    {
      path: '/dashboard',
      component: () => import('./AppLayout.vue'),
      meta: { authenticated: true },
      children: [
        {
          path: '',
          name: 'Dashboard',
          component: () => import('../features/home/HomeView.vue'),
          meta: { title: '我的家' }
        },
        {
          path: 'records',
          component: () => import('../features/activity/ActivityView.vue'),
          meta: { title: '动态' }
        },
        {
          path: 'guests',
          component: () => import('../features/guests/GuestsView.vue'),
          meta: { title: '访客' }
        },
        {
          path: 'alarms',
          component: () => import('../features/administration/AlarmsView.vue'),
          meta: { title: '报警', admin: true }
        },
        {
          path: 'users',
          component: () => import('../features/administration/UsersView.vue'),
          meta: { title: '用户与权限', admin: true }
        },
        {
          path: 'evidence',
          component: () => import('../features/security/EvidenceView.vue'),
          meta: { title: '安全证据', admin: true }
        },
        {
          path: 'security',
          component: () => import('../features/settings/SettingsView.vue'),
          meta: { title: '账户与安全' }
        }
      ]
    },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})
router.beforeEach((to) => {
  if (to.meta.authenticated && !localStorage.getItem('token')) return { name: 'UserLogin' }
  // Presentation guard; the server enforces authorization on every request.
  if (to.meta.admin && localStorage.getItem('role') !== 'admin') return { name: 'Dashboard' }
})
router.afterEach((to) => {
  document.title = `${to.meta.title || '控制台'} · SmartLock`
})
export default router
