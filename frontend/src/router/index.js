/**
 * Vue Router — all application routes
 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const routes = [
  {
    path: '/',
    name: 'landing',
    component: () => import('../views/LandingPage.vue'),
    meta: { public: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginPage.vue'),
    meta: { public: true },
  },
  {
    path: '/auth/callback',
    name: 'auth-callback',
    component: () => import('../views/AuthCallbackPage.vue'),
    meta: { public: true },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('../views/DashboardPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/editor',
    name: 'editor-new',
    component: () => import('../views/PaperEditorPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/editor/:paperId',
    name: 'editor',
    component: () => import('../views/PaperEditorPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('../views/AdminPage.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()

  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return next('/login')
  }
  if (to.meta.requiresAdmin && auth.user?.role !== 'admin') {
    return next('/dashboard')
  }
  if (to.meta.public && auth.isLoggedIn && (to.name === 'login' || to.name === 'landing')) {
    return next('/dashboard')
  }

  next()
})

export default router
