<script setup lang="ts">
import { onMounted } from 'vue'
import Sidebar from './components/Sidebar.vue'

// Prevent Electron default file-open behavior for drag-and-drop
// This allows Vue @drop handlers to work normally
onMounted(() => {
  document.addEventListener('dragover', (e) => {
    e.preventDefault()  // Required: tells browser we accept drops
  })
  document.addEventListener('drop', (e) => {
    // Only prevent default (navigation) — don't stop propagation
    // Vue @drop handlers fire BEFORE this (bubble up from element → document)
    e.preventDefault()
  })
})
</script>

<template>
  <div class="app-shell">
    <Sidebar />
    <main class="main-area">
      <router-view v-slot="{ Component }">
        <transition name="slide" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  padding-top: var(--titlebar-height);
}

.main-area {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px;
  background: var(--bg-base);
  position: relative;
}

/* Subtle gradient glow at top */
.main-area::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 200px;
  background: radial-gradient(
    ellipse 60% 50% at 50% 0%,
    hsla(var(--accent-h), 60%, 40%, 0.06) 0%,
    transparent 100%
  );
  pointer-events: none;
}
</style>
