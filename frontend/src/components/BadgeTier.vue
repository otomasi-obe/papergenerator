<template>
  <span
    v-if="badge"
    class="inline-flex items-center rounded-full font-bold uppercase relative overflow-hidden"
    :class="[
      sizeClasses[size],
      isElite
        ? 'badge-elite-gradient text-white badge-shimmer'
        : isPro
          ? 'badge-pro-gradient text-white'
          : [tierInfo?.color, tierInfo?.textColor]
    ]"
  >
    <span v-if="isElite" class="absolute inset-0 badge-shine pointer-events-none"></span>
    <span class="relative z-10 tracking-wider px-2">{{ tierInfo?.label }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BADGE_TIERS, type BadgeKey } from '../config/badgeTiers'

const props = defineProps<{
  badge: string | null | undefined
  size?: 'xs' | 'sm' | 'md'
}>()

const tierInfo = computed(() => {
  if (!props.badge) return null
  return BADGE_TIERS[props.badge as BadgeKey] ?? null
})

const isElite = computed(() => props.badge === 'elite')
const isPro = computed(() => props.badge === 'pro')

const sizeClasses = {
  xs: 'text-[9px] py-0',
  sm: 'text-[10px] py-0.5',
  md: 'text-xs py-1'
}
</script>

<style scoped>
/* Elite gradient: blue → indigo → violet → purple */
.badge-elite-gradient {
  background: linear-gradient(135deg, #0ea5e9 0%, #14b8a6 50%, #22c55e 100%);
  border: 1.5px solid rgba(255, 255, 255, 0.6);
  box-shadow:
    0 1px 3px rgba(14, 165, 233, 0.5),
    0 0 0 1px rgba(20, 184, 166, 0.3),
    0 0 12px rgba(20, 184, 166, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.3);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

/* Pro gradient: blue → indigo, static glow (no animation) */
.badge-pro-gradient {
  background: linear-gradient(135deg, #2563eb 0%, #3b82f6 40%, #4f46e5 100%);
  border: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow:
    0 1px 2px rgba(37, 99, 235, 0.4),
    0 0 0 1px rgba(59, 130, 246, 0.25),
    0 0 8px rgba(59, 130, 246, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.25);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
}

/* Shimmer sweep — smooth diagonal light band */
.badge-shimmer::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 60%;
  height: 100%;
  background: linear-gradient(
    105deg,
    transparent 20%,
    rgba(255, 255, 255, 0.55) 50%,
    transparent 80%
  );
  animation: shimmer-sweep 4s linear infinite;
  z-index: 5;
  pointer-events: none;
}

/* Glow pulse — slow breathing aura, seamless loop */
.badge-elite-gradient {
  animation: elite-glow 4s ease-in-out infinite;
}

@keyframes shimmer-sweep {
  0%   { left: -100%; }
  100% { left: 130%; }
}

@keyframes elite-glow {
  0%, 100% {
    box-shadow:
      0 1px 3px rgba(14, 165, 233, 0.5),
      0 0 0 1px rgba(20, 184, 166, 0.25),
      0 0 8px rgba(20, 184, 166, 0.3),
      0 0 16px rgba(34, 197, 94, 0.15),
      0 0 28px rgba(20, 184, 166, 0.05),
      inset 0 1px 0 rgba(255, 255, 255, 0.3);
  }
  25% {
    box-shadow:
      0 1px 3px rgba(14, 165, 233, 0.55),
      0 0 0 1.25px rgba(20, 184, 166, 0.35),
      0 0 10px rgba(20, 184, 166, 0.4),
      0 0 20px rgba(34, 197, 94, 0.22),
      0 0 34px rgba(20, 184, 166, 0.08),
      inset 0 1px 0 rgba(255, 255, 255, 0.35);
  }
  50% {
    box-shadow:
      0 1px 3px rgba(14, 165, 233, 0.6),
      0 0 0 1.5px rgba(20, 184, 166, 0.5),
      0 0 14px rgba(20, 184, 166, 0.6),
      0 0 28px rgba(34, 197, 94, 0.35),
      0 0 44px rgba(20, 184, 166, 0.15),
      inset 0 1px 0 rgba(255, 255, 255, 0.45);
  }
  75% {
    box-shadow:
      0 1px 3px rgba(14, 165, 233, 0.55),
      0 0 0 1.25px rgba(20, 184, 166, 0.35),
      0 0 10px rgba(20, 184, 166, 0.4),
      0 0 20px rgba(34, 197, 94, 0.22),
      0 0 34px rgba(20, 184, 166, 0.08),
      inset 0 1px 0 rgba(255, 255, 255, 0.35);
  }
}

/* Respect reduced motion */
@media (prefers-reduced-motion: reduce) {
  .badge-shimmer::before { animation: none; display: none; }
  .badge-elite-gradient { animation: none; }
}
</style>
