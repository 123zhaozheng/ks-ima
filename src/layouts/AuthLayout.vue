<template>
  <div class="auth-page">
    <aside class="auth-brand">
      <div class="auth-brand-inner">
        <div class="auth-brand-row">
          <img
            class="auth-brand-logo"
            src="/icons/icon-256x256.png"
            alt="Nya AI"
          >
          <span class="auth-brand-name">Nya AI</span>
        </div>
        <h1 class="auth-brand-slogan">
          一站式 AI 工作台
        </h1>
        <p class="auth-brand-desc">
          搜索、阅读、写作，都在同一个知识空间里完成。
        </p>
        <ul class="auth-brand-features">
          <li class="auth-brand-feature">
            <q-icon
              name="sym_o_search"
              size="20px"
            />
            <span>语义搜索，直达知识深处</span>
          </li>
          <li class="auth-brand-feature">
            <q-icon
              name="sym_o_forum"
              size="20px"
            />
            <span>知识库问答，每一句都有出处</span>
          </li>
          <li class="auth-brand-feature">
            <q-icon
              name="sym_o_folder_open"
              size="20px"
            />
            <span>文档与笔记，统一管理</span>
          </li>
        </ul>
      </div>
      <div class="auth-brand-footer">
        © 2026 Nya AI
      </div>
    </aside>

    <main class="auth-main">
      <div class="auth-mobile-brand">
        <img
          class="auth-mobile-logo"
          src="/icons/icon-256x256.png"
          alt="Nya AI"
        >
        <span class="auth-mobile-name">Nya AI</span>
      </div>
      <div class="auth-form-wrap">
        <div
          v-if="$route.meta.title"
          class="auth-head"
        >
          <div class="auth-title">
            {{ $route.meta.title }}
          </div>
          <div class="auth-subtitle">
            {{ subtitle }}
          </div>
        </div>
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const subtitles: Record<string, string> = {
  '/auth/sign-in': '使用您的账户继续',
  '/auth/sign-up': '创建账户，开始您的知识之旅',
  '/auth/reset-password': '为您的账户设置新密码',
  '/auth/accept-invite': '接受邀请，加入团队',
}
const subtitle = computed(() => subtitles[route.path] ?? '')
</script>

<style scoped>
/* Split-screen brand layout; flat selectors only (Chrome 109 policy). */
.auth-page {
  display: flex;
  min-height: 100vh;
  min-height: 100dvh;
  background-color: var(--tk-bg);
}

/* Brand panel (desktop left column) */
.auth-brand {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 45%;
  padding: var(--tk-space-8) var(--tk-space-16);
  color: #ffffff;
  background: linear-gradient(
    155deg,
    var(--tk-accent-deeper) 0%,
    var(--tk-accent-deep) 48%,
    var(--tk-accent) 100%
  );
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

/* Layered glow + hairline grid, white alpha only (no new hues). */
.auth-brand::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 82% 12%, rgba(255, 255, 255, 0.18) 0%, rgba(255, 255, 255, 0) 42%),
    radial-gradient(circle at 8% 88%, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0) 46%);
  pointer-events: none;
}

.auth-brand::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.05) 1px, rgba(255, 255, 255, 0) 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, rgba(255, 255, 255, 0) 1px);
  background-size: 44px 44px;
  pointer-events: none;
}

.auth-brand-inner {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 100%;
  max-width: 460px;
  margin: 0 auto;
}

.auth-brand-row {
  display: flex;
  align-items: center;
  gap: var(--tk-space-3);
}

.auth-brand-logo {
  width: 40px;
  height: 40px;
  padding: 5px;
  box-sizing: border-box;
  border-radius: var(--tk-radius-lg);
  background-color: rgba(255, 255, 255, 0.94);
}

.auth-brand-name {
  font-size: var(--tk-font-size-lg);
  font-weight: var(--tk-weight-semibold);
  letter-spacing: var(--tk-tracking-display);
}

.auth-brand-slogan {
  margin: var(--tk-space-10) 0 0;
  font-size: 38px;
  font-weight: var(--tk-weight-semibold);
  line-height: 1.25;
  letter-spacing: var(--tk-tracking-display);
}

.auth-brand-desc {
  margin: var(--tk-space-4) 0 0;
  font-size: var(--tk-font-size-md);
  line-height: var(--tk-lh-body);
  color: rgba(255, 255, 255, 0.78);
}

.auth-brand-features {
  margin: var(--tk-space-12) 0 0;
  padding: 0;
  list-style: none;
}

.auth-brand-feature {
  display: flex;
  align-items: center;
  gap: var(--tk-space-3);
  padding: var(--tk-space-3) 0;
  font-size: var(--tk-font-size-sm);
  color: rgba(255, 255, 255, 0.9);
}

.auth-brand-feature .q-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--tk-radius);
  background-color: rgba(255, 255, 255, 0.14);
  color: #ffffff;
}

.auth-brand-footer {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 460px;
  margin: 0 auto;
  font-size: var(--tk-font-size-xs);
  color: rgba(255, 255, 255, 0.6);
}

/* Form panel (right column) */
.auth-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--tk-space-8) var(--tk-space-4);
}

.auth-mobile-brand {
  display: none;
}

.auth-form-wrap {
  width: 100%;
  max-width: 400px;
}

.auth-head {
  margin-bottom: var(--tk-space-8);
}

.auth-title {
  font-size: 28px;
  font-weight: var(--tk-weight-semibold);
  line-height: var(--tk-lh-tight);
  letter-spacing: var(--tk-tracking-display);
  color: var(--tk-text);
}

.auth-subtitle {
  margin-top: var(--tk-space-2);
  font-size: var(--tk-font-size-sm);
  color: var(--tk-text-secondary);
}

/* Below the md breakpoint the brand panel folds into a compact top bar. */
@media (max-width: 1023px) {
  .auth-page {
    flex-direction: column;
  }

  .auth-brand {
    display: none;
  }

  .auth-main {
    justify-content: flex-start;
    padding-top: 15vh;
  }

  .auth-mobile-brand {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--tk-space-2);
    margin-bottom: var(--tk-space-8);
  }

  .auth-mobile-logo {
    width: 36px;
    height: 36px;
    border-radius: var(--tk-radius);
  }

  .auth-mobile-name {
    font-size: var(--tk-font-size-lg);
    font-weight: var(--tk-weight-semibold);
    color: var(--tk-text);
  }
}
</style>
