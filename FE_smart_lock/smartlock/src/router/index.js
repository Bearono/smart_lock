import { createRouter, createWebHistory } from 'vue-router'
const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/',
      name: 'UserLogin',
      component: () => import('../views/UserLogin.vue'),
      meta: { title: '登录' }
    },
    {
      path: '/guest',
      name: 'GuestVerify',
      component: () => import('../views/GuestVerify.vue'),
      meta: { title: '访客通行' }
    },
    {
      path: '/dashboard',
      component: () => import('../layouts/AppLayout.vue'),
      meta: { authenticated: true },
      children: [
        {
          path: '',
          name: 'Dashboard',
          component: () => import('../views/DoorsView.vue'),
          meta: { title: '门控' }
        },
        {
          path: 'records',
          component: () => import('../views/RecordsView.vue'),
          meta: { title: '记录' }
        },
        {
          path: 'guests',
          component: () => import('../views/GuestsView.vue'),
          meta: { title: '访客' }
        },
        {
          path: 'alarms',
          component: () => import('../views/AlarmsView.vue'),
          meta: { title: '报警', admin: true }
        },
        {
          path: 'users',
          component: () => import('../views/UsersView.vue'),
          meta: { title: '用户与权限', admin: true }
        },
        {
          path: 'security',
          component: () => import('../views/SecurityView.vue'),
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
