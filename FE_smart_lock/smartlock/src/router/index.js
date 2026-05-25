import Vue from 'vue'
import VueRouter from 'vue-router'
// 引入两个页面组件
import UserLogin from '../views/UserLogin.vue'
import SmartDashboard from '../views/SmartDashboard.vue'

Vue.use(VueRouter)

const routes = [
  {
    path: '/',
    name: 'UserLogin',
    component: UserLogin
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: SmartDashboard
  }
]

const router = new VueRouter({
  mode: 'history',
  base: process.env.BASE_URL,
  routes
})

export default router