<script setup lang="ts">
import { Download, Link, FolderOpen } from 'lucide-vue-next'
import { ref } from 'vue'

const url = ref('')
</script>

<template>
  <div class="view">
    <header class="view-head">
      <div class="head-top">
        <div class="head-icon"><Download :size="20" /></div>
        <h1 class="head-title">Download</h1>
      </div>
      <p class="head-sub">YouTube, TikTok, Instagram — yt-dlp powered</p>
    </header>

    <!-- URL Input -->
    <div class="input-group">
      <div class="input-icon"><Link :size="16" /></div>
      <input
        v-model="url"
        type="text"
        class="url-input"
        placeholder="Paste video URL here..."
      />
      <button class="btn-download" :disabled="!url">
        <Download :size="16" />
        <span>Download</span>
      </button>
    </div>

    <!-- Drop zone -->
    <div class="drop-zone">
      <FolderOpen :size="32" />
      <p class="drop-title">Downloads will appear here</p>
      <p class="drop-sub">Supports 1000+ sites via yt-dlp</p>
    </div>
  </div>
</template>

<style scoped>
.view { max-width: 700px; position: relative; }

.view-head { margin-bottom: 28px; }
.head-top { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.head-icon {
  width: 36px; height: 36px; border-radius: 10px;
  background: linear-gradient(135deg, var(--emerald), hsl(170, 65%, 45%));
  display: flex; align-items: center; justify-content: center;
  color: white; box-shadow: 0 2px 16px hsla(155, 65%, 50%, 0.25);
}
.head-title { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
.head-sub { color: var(--text-secondary); font-size: 13px; padding-left: 48px; }

.input-group {
  display: flex; align-items: center; gap: 0;
  background: var(--bg-card); border: 1px solid var(--border-default);
  border-radius: 12px; padding: 4px; margin-bottom: 20px;
  transition: border-color 0.2s ease;
}
.input-group:focus-within {
  border-color: var(--border-accent);
  box-shadow: 0 0 0 3px hsla(var(--accent-h), 60%, 50%, 0.06);
}

.input-icon {
  padding: 0 12px; color: var(--text-muted);
}

.url-input {
  flex: 1; padding: 10px 0; border: none; outline: none;
  background: transparent; color: var(--text-primary);
  font-size: 13px; font-family: inherit;
}
.url-input::placeholder { color: var(--text-muted); }

.btn-download {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: 8px; border: none;
  background: linear-gradient(135deg, var(--emerald), hsl(170, 65%, 45%));
  color: white; font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all 0.2s ease;
}
.btn-download:hover { box-shadow: 0 2px 12px hsla(155, 65%, 50%, 0.3); transform: translateY(-1px); }
.btn-download:disabled { opacity: 0.4; cursor: not-allowed; transform: none; box-shadow: none; }

.drop-zone {
  background: var(--bg-card); border: 1px dashed var(--border-default);
  border-radius: 14px; padding: 48px; text-align: center;
  color: var(--text-muted); transition: all 0.3s ease;
}
.drop-zone:hover { border-color: var(--border-hover); background: var(--bg-card-hover); }
.drop-title { font-size: 14px; font-weight: 500; margin-top: 12px; color: var(--text-secondary); }
.drop-sub { font-size: 12px; margin-top: 4px; }
</style>
