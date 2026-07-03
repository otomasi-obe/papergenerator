import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes: RouteRecordRaw[] = [
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
    path: '/settings',
    name: 'settings',
    component: () => import('../views/SettingsPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/files',
    name: 'files',
    component: () => import('../views/FilesPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/files/:paperId',
    name: 'files-paper',
    component: () => import('../views/FilesPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/test/payment',
    name: 'test-payment',
    component: () => import('../views/TestPaymentPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/tokens/purchase',
    name: 'token-purchase',
    component: () => import('../views/TokenPurchasePage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/tokens/checkout',
    name: 'token-checkout',
    component: () => import('../views/TokenCheckoutPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/tokens/pay',
    name: 'token-pay',
    component: () => import('../views/TokenPayPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/terms',
    name: 'terms',
    component: () => import('../views/TermsPage.vue'),
    meta: { public: true }
  },
  {
    path: '/refund',
    name: 'refund',
    component: () => import('../views/RefundPage.vue'),
    meta: { public: true }
  },
  {
    path: '/faq',
    name: 'faq',
    component: () => import('../views/FAQPage.vue'),
    meta: { public: true }
  },
  {
    path: '/contact',
    name: 'contact',
    component: () => import('../views/ContactPage.vue'),
    meta: { public: true }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore()

  // Auto-redirect: authenticated users visiting landing or login page → dashboard
  if (auth.isLoggedIn) {
    if (to.path === '/' || to.name === 'login') {
      return next('/dashboard')
    }
  }

  // Public routes bypass all checks immediately
  if (to.meta.public === true) {
    return next()
  }

  // Ensure user state is loaded before checking auth
  if (!auth.user && !auth._loaded) {
    try {
      await auth.fetchMe()
      // Re-check redirect after loading user state
      if (auth.isLoggedIn && (to.path === '/' || to.name === 'login')) {
        return next('/dashboard')
      }
    } catch {
      // silent — proceed with auth check
    }
  }

  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return next('/login')
  }
  if (to.meta.requiresAdmin && auth.user?.role !== 'admin') {
    return next('/dashboard')
  }
  if (to.meta.emailWhitelist && Array.isArray(to.meta.emailWhitelist)) {
    if (!auth.user?.email || !to.meta.emailWhitelist.includes(auth.user.email)) {
      return next('/dashboard')
    }
  }

  next()
})

export default router
