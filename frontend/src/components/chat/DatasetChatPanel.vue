<template>
  <aside class="chat-panel">
    <header class="chat-header">
      <div>
        <span class="eyebrow">SQLBot</span>
        <h2>{{ fileName }}</h2>
      </div>
      <el-tag size="small" effect="plain">{{ shortId(datasetId) }}</el-tag>
    </header>

    <div class="messages" aria-live="polite">
      <div v-if="activeMessages.length === 0" class="empty-chat">
        <div class="empty-orbit">
          <span class="empty-core">AI</span>
        </div>
        <h3>智能问数助手</h3>
        <p>{{ emptyStateText }}</p>
        <div v-if="!isHistoryLoading && suggestedQuestions.length > 0" class="suggestions">
          <button
            v-for="suggestion in suggestedQuestions"
            :key="suggestion"
            class="suggestion-chip"
            type="button"
            @click="submitSuggestedQuestion(suggestion)"
          >
            {{ suggestion }}
          </button>
        </div>
      </div>
      <template v-else>
        <article
          v-for="message in activeMessages"
          :key="message.id"
          class="message"
          :class="message.role"
        >
          <span class="role">{{ message.role === 'user' ? 'You' : 'Analyst' }}</span>
          <p v-if="message.role === 'user'">{{ message.content }}</p>
          <div v-else class="markdown-body" v-html="renderMarkdown(message.content)" />
          <details v-if="message.sql" class="sql-block">
            <summary>SQL</summary>
            <pre>{{ message.sql }}</pre>
          </details>
        </article>
      </template>
    </div>

    <form class="composer" @submit.prevent="submitQuestion">
      <div class="composer-box">
        <el-input
          v-model="question"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isLoading"
          maxlength="1200"
          placeholder="输入关于当前数据源的问题"
          type="textarea"
        />
        <el-button
          class="send-button"
          native-type="submit"
          type="primary"
          :loading="isLoading"
          :disabled="!question.trim()"
        >
          Send
        </el-button>
      </div>
    </form>
  </aside>
</template>

<script setup lang="ts">
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import { computed, reactive, ref, watch } from 'vue'

import {
  askDatasetQuestion,
  deleteDatasetChatMessages,
  listDatasetChatMessages,
  listDatasetChatSuggestions,
  type DatasetChatMessage
} from '../../api/chatApi'

const props = defineProps<{
  datasetId: string
  versionId: string
  fileName: string
}>()

const conversations = reactive<Record<string, DatasetChatMessage[]>>({})
const suggestionCache = reactive<Record<string, string[]>>({})
const question = ref('')
const isLoading = ref(false)
const isHistoryLoading = ref(false)
const isSuggestionsLoading = ref(false)
const markdown = new MarkdownIt({
  breaks: true,
  html: false,
  linkify: true
})

const conversationKey = computed(() => `${props.datasetId}:${props.versionId}`)
const activeMessages = computed(() => conversations[conversationKey.value] ?? [])
const suggestedQuestions = computed(() => suggestionCache[conversationKey.value] ?? [])
const emptyStateText = computed(() => {
  if (isHistoryLoading.value) {
    return '正在加载对话'
  }
  if (isSuggestionsLoading.value) {
    return '正在根据当前数据集生成建议问题'
  }
  return '您可以针对当前数据集进行追问分析'
})

const shortId = (id: string) => `${id.slice(0, 8)}...${id.slice(-6)}`
const renderMarkdown = (content: string) => DOMPurify.sanitize(markdown.render(content))

const appendMessage = (message: DatasetChatMessage) => {
  if (!conversations[conversationKey.value]) {
    conversations[conversationKey.value] = []
  }
  conversations[conversationKey.value].push(message)
}

const loadHistory = async () => {
  const key = conversationKey.value
  if (conversations[key]) {
    return
  }

  const datasetId = props.datasetId
  const versionId = props.versionId
  isHistoryLoading.value = true
  try {
    const messages = await listDatasetChatMessages(datasetId, versionId)
    conversations[key] = messages
  } catch {
    conversations[key] = []
  } finally {
    if (key === conversationKey.value) {
      isHistoryLoading.value = false
    }
  }
}

const loadSuggestions = async () => {
  const key = conversationKey.value
  if (suggestionCache[key]) {
    return
  }

  const datasetId = props.datasetId
  const versionId = props.versionId
  isSuggestionsLoading.value = true
  try {
    const response = await listDatasetChatSuggestions(datasetId, versionId)
    const suggestions = response.suggestions
      .map((suggestion) => suggestion.trim())
      .filter(Boolean)
      .slice(0, 3)

    suggestionCache[key] = suggestions
  } catch {
    suggestionCache[key] = []
  } finally {
    if (key === conversationKey.value) {
      isSuggestionsLoading.value = false
    }
  }
}

const loadConversation = async () => {
  await Promise.all([loadHistory(), loadSuggestions()])
}

const submitQuestion = async () => {
  const text = question.value.trim()
  if (!text || isLoading.value) {
    return
  }

  question.value = ''
  appendMessage({
    id: crypto.randomUUID(),
    role: 'user',
    content: text,
    created_at: new Date().toISOString()
  })
  isLoading.value = true
  try {
    const response = await askDatasetQuestion(props.datasetId, props.versionId, text)
    conversations[conversationKey.value] = response.messages
  } catch (error) {
    appendMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: error instanceof Error ? error.message : '请求失败',
      created_at: new Date().toISOString()
    })
  } finally {
    isLoading.value = false
  }
}

const submitSuggestedQuestion = async (suggestion: string) => {
  if (isLoading.value) {
    return
  }

  question.value = suggestion.replace(/^[^\p{L}\p{N}]+/u, '').trim()
  await submitQuestion()
}

const clearHistory = async () => {
  conversations[conversationKey.value] = []
  await deleteDatasetChatMessages(props.datasetId, props.versionId)
}

watch(conversationKey, loadConversation, { immediate: true })

defineExpose({ clearHistory })
</script>

<style scoped>
.chat-panel {
  display: grid;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  grid-template-rows: auto 1fr auto;
  background: #ffffff;
  border-left: 1px solid #dfe4ea;
}

.chat-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 18px 18px 16px;
  border-bottom: 1px solid #e6ebf0;
}

.eyebrow {
  color: #647386;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.chat-header h2 {
  max-width: 260px;
  margin: 5px 0 0;
  overflow-wrap: anywhere;
  color: #1a2633;
  font-size: 15px;
  line-height: 1.35;
}

.messages {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  overflow-y: auto;
  background: #f8fafc;
}

.empty-chat {
  display: grid;
  min-height: 100%;
  align-content: center;
  justify-items: center;
  gap: 10px;
  padding: 28px 10px;
  text-align: center;
}

.empty-orbit {
  display: grid;
  width: 64px;
  height: 64px;
  place-items: center;
  margin-bottom: 2px;
  background:
    radial-gradient(circle at 50% 50%, #ffffff 0 42%, transparent 43%),
    conic-gradient(from 140deg, #10b981, #60a5fa, #93c5fd, #10b981);
  border-radius: 999px;
  box-shadow: 0 10px 28px rgba(35, 87, 198, 0.14);
}

.empty-core {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  color: #047857;
  background: #ecfdf5;
  border: 1px solid #bbf7d0;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 900;
}

.empty-chat h3 {
  margin: 4px 0 0;
  color: #122033;
  font-size: 18px;
  line-height: 1.3;
}

.empty-chat p {
  max-width: 270px;
  margin: 0;
  color: #637386;
  font-size: 13px;
  line-height: 1.6;
}

.suggestions {
  display: grid;
  width: 100%;
  max-width: 306px;
  gap: 9px;
  margin-top: 10px;
}

.suggestion-chip {
  padding: 9px 12px;
  color: #23405f;
  text-align: left;
  cursor: pointer;
  background: #f3f8ff;
  border: 1px solid #dbeafe;
  border-radius: 999px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    background 180ms ease,
    box-shadow 180ms ease;
}

.suggestion-chip:hover {
  background: #f0fdf4;
  border-color: #86efac;
  box-shadow: 0 9px 18px rgba(16, 185, 129, 0.12);
  transform: translateY(-2px);
}

.message {
  max-width: 92%;
  padding: 12px 13px;
  background: #ffffff;
  border: 1px solid #dfe5ec;
  border-radius: 8px;
}

.message.user {
  align-self: flex-end;
  color: #ffffff;
  background: #2357c6;
  border-color: #2357c6;
}

.message.assistant {
  align-self: flex-start;
}

.role {
  display: block;
  margin-bottom: 5px;
  font-size: 11px;
  font-weight: 700;
  opacity: 0.72;
}

.message p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.55;
}

.markdown-body {
  color: #1f2f3f;
  font-size: 14px;
  line-height: 1.6;
}

.markdown-body :deep(p),
.markdown-body :deep(ul),
.markdown-body :deep(ol),
.markdown-body :deep(blockquote),
.markdown-body :deep(pre),
.markdown-body :deep(table) {
  margin: 0 0 10px;
}

.markdown-body :deep(p:last-child),
.markdown-body :deep(ul:last-child),
.markdown-body :deep(ol:last-child),
.markdown-body :deep(blockquote:last-child),
.markdown-body :deep(pre:last-child),
.markdown-body :deep(table:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
}

.markdown-body :deep(li + li) {
  margin-top: 4px;
}

.markdown-body :deep(strong) {
  color: #142236;
  font-weight: 800;
}

.markdown-body :deep(a) {
  color: #2357c6;
  font-weight: 700;
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(code) {
  padding: 2px 5px;
  color: #1f3657;
  background: #e9f0fb;
  border-radius: 4px;
  font-size: 12px;
}

.markdown-body :deep(pre) {
  max-width: 100%;
  overflow-x: auto;
  padding: 10px;
  color: #d7e8ff;
  background: #122033;
  border-radius: 6px;
}

.markdown-body :deep(pre code) {
  padding: 0;
  color: inherit;
  background: transparent;
}

.markdown-body :deep(blockquote) {
  padding-left: 10px;
  color: #55687d;
  border-left: 3px solid #b7c8dc;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 6px 8px;
  border: 1px solid #dce5ee;
}

.markdown-body :deep(th) {
  background: #f1f5f9;
}

.sql-block {
  margin-top: 10px;
  color: #1f2f3f;
}

.sql-block summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.sql-block pre {
  max-width: 100%;
  overflow-x: auto;
  padding: 10px;
  color: #d7e8ff;
  background: #122033;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.45;
}

.composer {
  padding: 14px;
  background: #ffffff;
  border-top: 1px solid #e6ebf0;
}

.composer-box {
  position: relative;
  padding: 8px;
  background: #f8fafc;
  border: 1px solid #d9e4ef;
  border-radius: 10px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  transition: border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
}

.composer-box:focus-within {
  background: #ffffff;
  border-color: #10b981;
  box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.22);
}

.composer-box :deep(.el-textarea__inner) {
  min-height: 76px !important;
  padding: 8px 92px 10px 10px;
  background: transparent;
  border: 0;
  box-shadow: none;
  resize: none;
}

.send-button {
  position: absolute;
  right: 12px;
  bottom: 12px;
  min-height: 32px;
  padding: 6px 13px;
  border-radius: 8px;
  font-weight: 800;
}

@media (max-width: 1180px) {
  .chat-panel {
    height: 520px;
    min-height: 520px;
    border-top: 1px solid #dfe4ea;
    border-left: 0;
  }
}
</style>
