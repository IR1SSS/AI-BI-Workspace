import { createRouter, createWebHistory } from 'vue-router'

import DashboardView from './views/dashboards/DashboardView.vue'
import DatasetView from './views/datasets/DatasetView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/datasets' },
    { path: '/datasets', component: DatasetView },
    { path: '/dashboards', component: DashboardView }
  ]
})

export default router

