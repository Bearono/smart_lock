import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import '../shared/styles/app.css'
import { glassMaterials } from '../shared/material/glass.ts'

createApp(App).use(glassMaterials).use(router).mount('#app')
