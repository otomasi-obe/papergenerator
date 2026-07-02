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

console.log('[Router] Router instance created')

router.beforeEach(async (to, _from, next) => {
  console.log('[Router Guard] START', {
    to: to.path,
    toName: to.name,
    meta: to.meta,
  })

  const auth = useAuthStore()

  console.log('[Router Guard] Auth store loaded', {
    isLoggedIn: auth.isLoggedIn,
    userLoaded: auth._loaded
  })

  // Auto-redirect: authenticated users visiting landing or login page → dashboard
  if (auth.isLoggedIn) {
    if (to.path === '/' || to.name === 'login') {
      console.log('[Router Guard] Already logged in, redirecting to /dashboard')
      return next('/dashboard')
    }
  }

  // Public routes bypass all checks immediately
  if (to.meta.public === true) {
    console.log('[Router Guard] Public route detected, allowing access')
    return next()
  }

  // Ensure user state is loaded before checking auth
  if (!auth.user && !auth._loaded) {
    console.log('[Router Guard] Loading user state...')
    try { 
      await auth.fetchMe() 
      console.log('[Router Guard] User state loaded:', { isLoggedIn: auth.isLoggedIn })
      
      // Re-check redirect after loading user state
      if (auth.isLoggedIn && (to.path === '/' || to.name === 'login')) {
        return next('/dashboard')
      }
    } catch (err) {
      console.error('[Router Guard] fetchMe failed:', err)
    }
  }

  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    console.log('[Router Guard] Auth required but not logged in, redirecting to /login')
    return next('/login')
  }
  if (to.meta.requiresAdmin && auth.user?.role !== 'admin') {
    console.log('[Router Guard] Admin required, redirecting to /dashboard')
    return next('/dashboard')
  }
  if (to.meta.emailWhitelist && Array.isArray(to.meta.emailWhitelist)) {
    if (!auth.user?.email || !to.meta.emailWhitelist.includes(auth.user.email)) {
      console.log('[Router Guard] Email not whitelisted, redirecting to /dashboard')
      return next('/dashboard')
    }
  }

  console.log('[Router Guard] Allowing navigation')
  next()
})

export default router
