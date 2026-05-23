<template>
  <section class="dashboard-page">
    <header class="page-header dashboard-header">
      <div>
        <h1>Dashboards</h1>
      </div>
    </header>

    <div v-if="dashboards.length === 0" class="empty-state">
      <el-empty description="No dashboard draft generated yet" />
    </div>

    <div v-else class="dashboard-workbench">
      <aside class="dataset-rail">
        <div class="rail-header">
          <span>Data Sources</span>
          <b>{{ dashboards.length }}</b>
        </div>
        <div
          v-for="dashboard in dashboards"
          :key="dashboard.id"
          class="dataset-item"
          :class="{ active: dashboard.id === selectedDashboardId }"
        >
          <button class="dataset-select" type="button" @click="selectedDashboardId = dashboard.id">
            <span class="dataset-name">{{ datasetName(dashboard) }}</span>
            <span class="dataset-meta">
              <el-tooltip :content="dashboard.dataset_id" placement="top">
                <code>{{ shortId(dashboard.dataset_id) }}</code>
              </el-tooltip>
            </span>
            <span class="dataset-tags">
              <el-tag size="small" type="success">{{ dashboard.status }}</el-tag>
              <el-tag v-if="dashboard.analysis_source" size="small" type="info">
                {{ dashboard.analysis_source === 'llm' ? 'AI' : 'Fallback' }}
              </el-tag>
            </span>
          </button>
          <button
            class="rail-icon-button clear-chat"
            type="button"
            aria-label="Clear ChatBI conversation"
            title="Clear ChatBI conversation"
            @click="clearConversation(dashboard)"
          >
            <ChatDotRoundIcon class="rail-icon" aria-hidden="true" />
          </button>
          <button
            class="rail-icon-button delete-dataset"
            type="button"
            aria-label="Delete dataset version"
            title="Delete dataset version"
            @click="deleteDataset(dashboard)"
          >
            <DeleteIcon class="rail-icon" aria-hidden="true" />
          </button>
        </div>
      </aside>

      <main v-if="activeDashboard" class="dashboard-stage">
        <div class="stage-toolbar">
          <div>
            <h2>{{ activeDashboard.title }}</h2>
            <p>
              Dataset
              <el-tooltip :content="activeDashboard.dataset_id" placement="top">
                <code>{{ shortId(activeDashboard.dataset_id) }}</code>
              </el-tooltip>
            </p>
          </div>
          <div class="stage-stats">
            <span>{{ metricCards.length }} metrics</span>
            <span>{{ chartCards.length }} charts</span>
            <button class="report-button" type="button" :disabled="isReportLoading" @click="generateReport">
              {{ reportButtonText }}
            </button>
          </div>
        </div>

        <el-alert
          v-if="reportJob && reportJob.status !== 'succeeded'"
          class="report-job-alert"
          :type="reportJob.status === 'failed' ? 'error' : 'info'"
          :title="reportJobTitle"
          show-icon
          :closable="false"
        />

        <section v-if="activeDashboard.report" class="report-panel">
          <div>
            <span class="eyebrow">Report Agent</span>
            <h3>{{ activeDashboard.report.title }}</h3>
            <p>{{ activeDashboard.report.executive_summary }}</p>
          </div>
          <div class="report-sections">
            <article v-for="section in activeDashboard.report.sections" :key="section.title">
              <h4>{{ section.title }}</h4>
              <p>{{ section.body }}</p>
            </article>
          </div>
          <ul class="next-actions">
            <li v-for="action in activeDashboard.report.next_actions" :key="action">{{ action }}</li>
          </ul>
        </section>

        <div class="metric-strip">
          <DashboardCard v-for="card in metricCards" :key="card.id" :card="card" />
        </div>

        <div class="visual-board">
          <DashboardCard v-for="card in chartCards" :key="card.id" :card="card" />
        </div>
      </main>

      <DatasetChatPanel
        v-if="activeDashboard"
        :key="`${activeDashboard.dataset_id}:${activeDashboard.version_id}:${chatPanelRefreshKey}`"
        :dataset-id="activeDashboard.dataset_id"
        :version-id="activeDashboard.version_id"
        :file-name="datasetName(activeDashboard)"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { ChatDotRound as ChatDotRoundIcon, Delete as DeleteIcon } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import {
  createDashboardReportJob,
  deleteDatasetVersion,
  getJob,
  listDashboards,
  type DashboardReport,
  type DashboardDraft,
  type JobRecord
} from '../../api/datasetApi'
import { deleteDatasetChatMessages } from '../../api/chatApi'
import DatasetChatPanel from '../../components/chat/DatasetChatPanel.vue'
import DashboardCard from '../../components/chart-renderer/DashboardCard.vue'

const dashboards = ref<DashboardDraft[]>([])
const selectedDashboardId = ref('')
const isReportLoading = ref(false)
const chatPanelRefreshKey = ref(0)
const reportJob = ref<JobRecord<DashboardReport> | null>(null)

const activeDashboard = computed(() =>
  dashboards.value.find(dashboard => dashboard.id === selectedDashboardId.value) ?? dashboards.value[0]
)
const visibleCards = computed(() => activeDashboard.value?.cards.filter(card => card.type !== 'text') ?? [])
const metricCards = computed(() => visibleCards.value.filter(card => card.type === 'metric'))
const chartCards = computed(() => visibleCards.value.filter(card => card.type === 'chart'))
const reportButtonText = computed(() => {
  if (isReportLoading.value) {
    return 'Generating...'
  }
  return activeDashboard.value?.report ? 'Regenerate report' : 'Generate report'
})
const reportJobTitle = computed(() => {
  if (!reportJob.value) {
    return ''
  }
  if (reportJob.value.status === 'failed') {
    return `Report job failed: ${reportJob.value.error}`
  }
  return `Report job ${shortId(reportJob.value.job_id)} is ${reportJob.value.status}.`
})

const shortId = (id: string) => `${id.slice(0, 8)}...${id.slice(-6)}`
const datasetName = (dashboard: DashboardDraft) =>
  (dashboard.file_name || dashboard.title)
    .replace(/^Dashboard Draft for\s+/i, '')
    .replace(/\s+Dashboard Draft$/i, '')

const updateActiveDashboard = (patch: Partial<DashboardDraft>) => {
  if (!activeDashboard.value) {
    return
  }
  const index = dashboards.value.findIndex(dashboard => dashboard.id === activeDashboard.value?.id)
  if (index >= 0) {
    dashboards.value[index] = { ...dashboards.value[index], ...patch }
  }
}

const generateReport = async () => {
  if (!activeDashboard.value || isReportLoading.value) {
    return
  }

  isReportLoading.value = true
  reportJob.value = null
  try {
    const job = await createDashboardReportJob(
      activeDashboard.value.dataset_id,
      activeDashboard.value.version_id
    )
    reportJob.value = job
    const completedJob = await waitForReportJob(job.job_id)
    if (completedJob.status === 'failed' || !completedJob.result) {
      throw new Error(completedJob.error || 'Report job failed')
    }
    const report = completedJob.result
    updateActiveDashboard({ report })
    ElMessage.success('Report generated.')
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'Report generation failed')
  } finally {
    isReportLoading.value = false
  }
}

const sleep = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

const waitForReportJob = async (jobId: string) => {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const job = await getJob<DashboardReport>(jobId)
    reportJob.value = job
    if (job.status === 'succeeded' || job.status === 'failed') {
      return job
    }
    await sleep(1000)
  }
  throw new Error('Report job timed out')
}

const clearConversation = async (dashboard: DashboardDraft) => {
  if (!window.confirm(`Clear the ChatBI conversation for ${datasetName(dashboard)}?`)) {
    return
  }

  await deleteDatasetChatMessages(dashboard.dataset_id, dashboard.version_id)
  chatPanelRefreshKey.value += 1
  ElMessage.success('Conversation cleared.')
}

const deleteDataset = async (dashboard: DashboardDraft) => {
  const name = datasetName(dashboard)
  if (!window.confirm(`Delete dataset version ${name}? This removes raw data, dashboard, report, and chat history.`)) {
    return
  }

  await deleteDatasetVersion(dashboard.dataset_id, dashboard.version_id)
  dashboards.value = dashboards.value.filter(item => item.id !== dashboard.id)
  if (dashboard.id === selectedDashboardId.value) {
    selectedDashboardId.value = dashboards.value[0]?.id ?? ''
  }
  ElMessage.success('Dataset version deleted.')
}

watch(dashboards, value => {
  if (!selectedDashboardId.value && value.length > 0) {
    selectedDashboardId.value = value[0].id
  }
})

onMounted(async () => {
  dashboards.value = await listDashboards()
})
</script>

<style scoped>
.dashboard-page {
  min-height: calc(100vh - 56px);
}

.dashboard-header {
  position: relative;
  margin-bottom: 18px;
  padding: 2px 0 4px;
}

.eyebrow {
  display: inline-block;
  margin-bottom: 4px;
  color: #2357c6;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.dashboard-header h1 {
  margin: 0;
  color: #142236;
  font-size: 34px;
  line-height: 1.2;
  letter-spacing: 0;
}

.dashboard-header p {
  margin: 8px 0 0;
  color: #5f6f82;
}

.empty-state {
  padding: 36px;
  background: #ffffff;
  border: 1px solid #dfe5ec;
  border-radius: 8px;
}

.dashboard-workbench {
  display: grid;
  height: calc(100vh - 150px);
  min-height: 620px;
  grid-template-columns: 280px minmax(0, 1fr) 380px;
  background: #eef3f8;
  border: 1px solid #d9e1ea;
  border-radius: 8px;
  overflow: hidden;
}

.dataset-rail {
  padding: 14px;
  overflow-y: auto;
  background: #ffffff;
  border-right: 1px solid #dfe4ea;
  scrollbar-color: transparent transparent;
  scrollbar-width: thin;
  transition: scrollbar-color 180ms ease;
}

.dataset-rail:hover {
  scrollbar-color: rgba(100, 116, 139, 0.28) transparent;
}

.dataset-rail::-webkit-scrollbar {
  width: 5px;
  height: 5px;
}

.dataset-rail::-webkit-scrollbar-track {
  background: transparent;
}

.dataset-rail::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 999px;
}

.dataset-rail:hover::-webkit-scrollbar-thumb {
  background: rgba(100, 116, 139, 0.28);
}

.dataset-rail:hover::-webkit-scrollbar-thumb:hover {
  background: rgba(71, 85, 105, 0.45);
}

.rail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 4px 12px;
  color: #5e6f82;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.rail-header b {
  color: #142236;
  font-size: 13px;
}

.dataset-item {
  display: grid;
  position: relative;
  width: 100%;
  gap: 8px;
  padding: 12px;
  margin-bottom: 8px;
  background: #f8fafc;
  border: 1px solid #e3e8ee;
  border-radius: 8px;
  transition: background 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
}

.dataset-item:hover,
.dataset-item.active {
  background: #eef5ff;
  border-color: #9bb9f4;
  box-shadow: 0 8px 20px rgba(35, 87, 198, 0.1);
}

.dataset-select {
  display: grid;
  width: 100%;
  gap: 8px;
  padding: 0 32px 0 0;
  color: #263648;
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: 0;
}

.dataset-name {
  overflow-wrap: anywhere;
  font-weight: 700;
  line-height: 1.35;
}

.dataset-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #66778a;
  font-size: 12px;
}

.dataset-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rail-icon-button {
  position: absolute;
  top: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  color: #7a8795;
  cursor: pointer;
  pointer-events: none;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  opacity: 0;
  transition: color 160ms ease, background 160ms ease, border-color 160ms ease, opacity 160ms ease;
}

.clear-chat {
  right: 44px;
}

.delete-dataset {
  right: 8px;
}

.dataset-item:hover .rail-icon-button,
.dataset-item:focus-within .rail-icon-button {
  pointer-events: auto;
  opacity: 1;
}

.clear-chat:hover {
  color: #2357c6;
  background: #edf5ff;
  border-color: #c8dcfa;
}

.delete-dataset:hover {
  color: #b42318;
  background: #fff1f1;
  border-color: #f0c7c7;
}

.rail-icon {
  width: 16px;
  height: 16px;
}

.dashboard-stage {
  min-width: 0;
  min-height: 0;
  padding: 18px;
  overflow-y: auto;
}

.stage-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.report-job-alert {
  margin-bottom: 14px;
}

.stage-toolbar h2 {
  margin: 0;
  color: #142236;
  font-size: 21px;
  line-height: 1.3;
}

.stage-toolbar p {
  margin: 7px 0 0;
  color: #607184;
}

.stage-stats {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.stage-stats span {
  padding: 6px 9px;
  color: #25384c;
  background: #ffffff;
  border: 1px solid #dfe5ec;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
}

.report-button {
  min-height: 34px;
  padding: 6px 12px;
  color: #ffffff;
  cursor: pointer;
  background: #2357c6;
  border: 1px solid #2357c6;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 800;
}

.report-button:disabled {
  cursor: wait;
  opacity: 0.6;
}

.report-panel {
  display: grid;
  gap: 14px;
  margin-bottom: 16px;
  padding: 16px;
  background: #ffffff;
  border: 1px solid #dfe5ec;
  border-radius: 8px;
}

.report-panel h3 {
  margin: 4px 0 8px;
  color: #142236;
  font-size: 18px;
}

.report-panel p {
  margin: 0;
  color: #526376;
  line-height: 1.6;
  white-space: pre-wrap;
}

.report-sections {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.report-sections article {
  padding-top: 10px;
  border-top: 1px solid #e5ebf1;
}

.report-sections h4 {
  margin: 0 0 6px;
  color: #172433;
  font-size: 14px;
}

.next-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.next-actions li {
  padding: 6px 9px;
  color: #22436f;
  background: #edf5ff;
  border: 1px solid #d5e6fb;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(96px, 138px));
  gap: 8px;
  align-items: stretch;
  margin-bottom: 12px;
}

.visual-board {
  display: grid;
  grid-auto-flow: dense;
  grid-auto-rows: minmax(238px, auto);
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 12px;
  background: #ffffff;
  border: 1px solid #e7edf4;
  border-radius: 8px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
}

code {
  padding: 2px 5px;
  color: #1f3657;
  background: #e9f0fb;
  border-radius: 4px;
}

@media (max-width: 1380px) {
  .dashboard-workbench {
    grid-template-columns: 248px minmax(0, 1fr) 340px;
  }
}

@media (max-width: 1180px) {
  .dashboard-workbench {
    grid-template-columns: 240px minmax(0, 1fr);
    height: auto;
  }

  :deep(.chat-panel) {
    grid-column: 1 / -1;
  }
}

@media (max-width: 780px) {
  .dashboard-workbench {
    grid-template-columns: 1fr;
  }

  .dataset-rail {
    max-height: 300px;
    border-right: 0;
    border-bottom: 1px solid #dfe4ea;
  }

  .stage-toolbar {
    display: grid;
  }

  .stage-stats {
    justify-content: flex-start;
  }

  .metric-strip {
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  }

  .visual-board {
    grid-template-columns: 1fr;
  }

  :deep(.dashboard-card.chart.size-wide),
  :deep(.dashboard-card.chart.size-hero) {
    grid-column: span 1;
  }
}
</style>
