<template>
  <welcome-wrapper>
    <q-card
      flat
      bg-sur
      max-w="600px"
    >
      <q-card-section>
        <div class="text-h6">
          {{ t('Notes') }}
        </div>
      </q-card-section>
      <q-card-section>
        <div>
          {{ t('Lightweight Markdown notes stored in the knowledge directory. Ask Copilot with citations, or expose them to other agents via connectors.') }}
        </div>
        <div mt-2>
          {{ t('Features:') }}
          <ul
            pl-4
            my-2
          >
            <li>{{ t('Markdown editing with autosave') }}</li>
            <li>{{ t('Folders and tags') }}</li>
            <li>{{ t('Full-text search and knowledge Q&A') }}</li>
          </ul>
        </div>
      </q-card-section>
    </q-card>
  </welcome-wrapper>
</template>

<script setup lang="ts">
import WelcomeWrapper from './WelcomeWrapper.vue'
import { t } from 'src/utils/i18n'
</script>
