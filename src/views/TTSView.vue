<script setup lang="ts">
import { AudioLines, Cloud, HardDrive } from 'lucide-vue-next'
</script>

<template>
  <div class="view">
    <header class="view-head">
      <div class="head-top">
        <div class="head-icon"><AudioLines :size="20" /></div>
        <h1 class="head-title">Text to Speech</h1>
      </div>
      <p class="head-sub">Multilingual TTS — EN, VN, JA, KO, DE, FR</p>
    </header>

    <div class="cards">
      <div class="card card--emerald">
        <div class="card-glow" />
        <div class="card-head">
          <div class="card-icon"><Cloud :size="22" /></div>
          <span class="card-badge">INSTANT</span>
        </div>
        <h3 class="card-title">Cloud TTS</h3>
        <p class="card-desc">
          EdgeTTS (free, instant) • ElevenLabs • Minimax — không cần download
        </p>
        <div class="card-action">
          <span>Default provider</span>
        </div>
      </div>

      <div class="card card--violet">
        <div class="card-glow" />
        <div class="card-head">
          <div class="card-icon"><HardDrive :size="22" /></div>
          <span class="card-badge">LOCAL</span>
        </div>
        <h3 class="card-title">Local TTS</h3>
        <p class="card-desc">
          Kokoro (82M, CPU) • XTTS-v2 • F5-TTS — on-demand download, offline
        </p>
        <div class="card-action">
          <span>Phase 4</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.view { max-width: 880px; position: relative; }

.view-head { margin-bottom: 32px; }
.head-top { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.head-icon {
  width: 36px; height: 36px; border-radius: 10px;
  background: linear-gradient(135deg, var(--pink), hsl(300, 70%, 55%));
  display: flex; align-items: center; justify-content: center;
  color: white; box-shadow: 0 2px 16px hsla(330, 80%, 65%, 0.25);
}
.head-title { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
.head-sub { color: var(--text-secondary); font-size: 13px; padding-left: 48px; }

.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.card {
  background: var(--bg-card); border: 1px solid var(--border-default);
  border-radius: 14px; padding: 24px; position: relative; overflow: hidden;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.card:hover { border-color: var(--border-hover); transform: translateY(-2px); background: var(--bg-card-hover); }

.card-glow {
  position: absolute; top: -40px; right: -40px;
  width: 120px; height: 120px; border-radius: 50%;
  opacity: 0; transition: opacity 0.4s ease; pointer-events: none;
}
.card:hover .card-glow { opacity: 1; }
.card--emerald .card-glow { background: radial-gradient(circle, hsla(155, 65%, 50%, 0.08), transparent); }
.card--violet .card-glow { background: radial-gradient(circle, hsla(var(--accent-h), 80%, 64%, 0.08), transparent); }

.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.card-icon {
  width: 44px; height: 44px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--border-subtle);
}
.card--emerald .card-icon { background: hsla(155, 65%, 50%, 0.08); color: var(--emerald); }
.card--violet .card-icon { background: hsla(var(--accent-h), 80%, 64%, 0.08); color: var(--accent); }

.card-badge {
  font-size: 10px; font-weight: 700; letter-spacing: 0.5px;
  padding: 3px 8px; border-radius: 5px;
  background: rgba(255, 255, 255, 0.04); color: var(--text-muted);
}
.card-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.card-desc { color: var(--text-secondary); font-size: 13px; line-height: 1.6; margin-bottom: 20px; }
.card-action { font-size: 12px; font-weight: 500; color: var(--text-muted); }
</style>
