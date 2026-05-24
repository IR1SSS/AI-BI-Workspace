<template>
  <section>
    <div class="page-header">
      <div>
        <h1>Datasets</h1>
        <p>Import files, normalize them to Parquet, and start automated analysis.</p>
      </div>
      <el-upload
        :auto-upload="false"
        :show-file-list="false"
        :on-change="handleFile"
        accept=".csv,.json,.jsonl,.xls,.xlsx"
      >
        <el-button type="primary" :loading="isUploading">Import File</el-button>
      </el-upload>
    </div>

    <div class="status-grid">
      <div class="panel">
        <h2>Import Status</h2>
        <el-alert
          v-if="uploadError"
          :title="uploadError"
          type="error"
          show-icon
          :closable="false"
          class="status-alert"
        />
        <el-alert
          v-if="successMessage"
          :title="successMessage"
          type="success"
          show-icon
          :closable="false"
          class="status-alert"
        />
        <el-alert
          v-if="activeJob && activeJob.status !== 'succeeded'"
          :title="jobStatusTitle"
          :type="activeJob.status === 'failed' ? 'error' : 'info'"
          show-icon
          :closable="false"
          class="status-alert"
        />
        <el-empty v-if="!lastImport && !isUploading" description="No dataset imported yet" />
        <el-skeleton v-if="isUploading" :rows="3" animated />
        <el-descriptions v-if="lastImport" title="Last Import" :column="1" border>
          <el-descriptions-item label="Dataset ID">
            <el-tooltip :content="lastImport.dataset_id" placement="top">
              <code>{{ shortId(lastImport.dataset_id) }}</code>
            </el-tooltip>
          </el-descriptions-item>
          <el-descriptions-item label="File">{{ lastImport.file_name }}</el-descriptions-item>
          <el-descriptions-item label="Rows">{{ lastImport.row_count }}</el-descriptions-item>
          <el-descriptions-item label="Columns">{{ lastImport.column_count }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <div class="panel">
        <div class="llm-heading">
          <h2>LLM Runtime</h2>
          <el-button size="small" :loading="isTestingLlm" @click="testLlmConnection">
            Test
          </el-button>
        </div>
        <el-descriptions v-if="llmConfig" :column="1" border>
          <el-descriptions-item label="Provider">{{ llmConfig.provider }}</el-descriptions-item>
          <el-descriptions-item label="Model">{{ llmConfig.model }}</el-descriptions-item>
          <el-descriptions-item label="API Key">
            {{ llmConfig.api_key_configured ? 'Configured' : 'Missing' }}
          </el-descriptions-item>
          <el-descriptions-item label="Status">
            <span class="online-status"><i /> Online</span>
          </el-descriptions-item>
          <el-descriptions-item label="Tokens Consumed">
            1,240 tokens <span class="session-label">(Session)</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="llmHealth" label="Health">
            <el-tag :type="llmHealth.status === 'ok' ? 'success' : 'danger'">
              {{ llmHealth.status }}
            </el-tag>
            <span class="health-detail">
              {{ llmHealth.status === 'ok' ? `${llmHealth.latency_ms} ms` : llmHealth.error }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-else-if="llmError"
          :title="llmError"
          type="error"
          show-icon
          :closable="false"
        />
        <el-empty v-else description="Loading LLM config" />
      </div>
    </div>

    <div class="panel import-history">
      <h2>Recent Imports</h2>
      <el-empty v-if="imports.length === 0" description="No imports in this browser session" />
      <el-table v-else :data="imports" size="small">
        <el-table-column prop="file_name" label="File" />
        <el-table-column label="Dataset ID" width="180">
          <template #default="{ row }">
            <el-tooltip :content="row.dataset_id" placement="top">
              <code>{{ shortId(row.dataset_id) }}</code>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="row_count" label="Rows" width="100" />
        <el-table-column prop="column_count" label="Columns" width="100" />
      </el-table>
    </div>

    <div class="panel">
      <h2>Next Pipeline Steps</h2>
      <div class="pipeline-steps" :style="{ '--pipeline-progress': pipelineProgress }">
        <div
          v-for="(step, index) in pipelineSteps"
          :key="step"
          class="pipeline-step"
          :class="{
            completed: index < pipelineActiveStep,
            active: index === pipelineActiveStep && pipelineActiveStep < pipelineSteps.length
          }"
        >
          <span class="step-badge">
            <span v-if="index < pipelineActiveStep">✓</span>
            <span v-else>{{ index + 1 }}</span>
          </span>
          <span class="step-title">{{ step }}</span>
        </div>
      </div>
    </div>

    <div v-if="profile" class="panel profile-panel">
      <h2>Profile Summary</h2>
      <el-alert
        v-if="profile.quality_issues.length > 0"
        :title="`${profile.quality_issues.length} data quality issue(s) detected`"
        type="warning"
        show-icon
        :closable="false"
        class="status-alert"
      />
      <div v-if="profile.quality_issues.length > 0" class="quality-strip">
        <el-tag
          v-for="issue in profile.quality_issues"
          :key="`${issue.type}:${issue.column ?? 'dataset'}`"
          :type="qualityTagType(issue.severity)"
          effect="plain"
        >
          {{ issueLabel(issue) }}
        </el-tag>
      </div>
      <el-table :data="profile.columns" size="small" max-height="360">
        <el-table-column prop="name" label="Column" min-width="160" />
        <el-table-column prop="data_type" label="Type" width="140" />
        <el-table-column prop="null_count" label="Nulls" width="100" />
        <el-table-column prop="unique_count" label="Unique" width="100" />
        <el-table-column label="Completeness" width="130">
          <template #default="{ row }">
            {{ percent(1 - row.null_ratio) }}
          </template>
        </el-table-column>
        <el-table-column label="Role" width="130">
          <template #default="{ row }">
            <el-tag v-if="row.is_probable_index" type="warning">Index-like</el-tag>
            <el-tag v-else-if="row.is_probable_identifier" type="info">Identifier</el-tag>
            <el-tag v-else-if="row.is_constant" type="info">Constant</el-tag>
            <el-tag v-else-if="row.is_numeric" type="success">Numeric</el-tag>
            <el-tag v-else>Dimension</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="preview" class="panel data-preview-panel">
      <div class="panel-heading">
        <h2>Data Preview</h2>
        <span>{{ preview.rows.length }} sample rows</span>
      </div>
      <el-table :data="preview.rows" size="small" max-height="320">
        <el-table-column
          v-for="column in preview.columns"
          :key="column"
          :label="column"
          min-width="150"
          show-overflow-tooltip
        >
          <template #default="{ row }">{{ formatCell(row[column]) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="cleaningPlan" class="panel cleaning-panel">
      <div class="panel-heading">
        <div>
          <h2>Cleaning Plan</h2>
          <p>
            {{ selectedCleaningOperationIds.length }} of {{ cleaningPlan.operation_count }}
            operation(s) selected.
          </p>
        </div>
        <div class="cleaning-actions">
          <el-button :disabled="selectedCleaningOperationIds.length === 0" @click="loadCleaningPreview">
            Preview
          </el-button>
          <el-button
            type="primary"
            :loading="isCleaning"
            :disabled="selectedCleaningOperationIds.length === 0"
            @click="executeCleaningPlan"
          >
            Execute
          </el-button>
        </div>
      </div>
      <el-empty v-if="cleaningPlan.operation_count === 0" description="No cleaning action needed" />
      <el-table v-else :data="cleaningPlan.operations" size="small">
        <el-table-column label="" width="56">
          <template #default="{ row }">
            <el-checkbox
              :model-value="selectedCleaningOperationIds.includes(row.id)"
              @change="toggleCleaningOperation(row.id)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="operation_type" label="Operation" width="170" />
        <el-table-column prop="target_column" label="Column" width="180">
          <template #default="{ row }">{{ row.target_column || 'Dataset' }}</template>
        </el-table-column>
        <el-table-column prop="rationale" label="Rationale" min-width="260" />
      </el-table>

      <el-alert
        v-if="cleaningPreview"
        class="status-alert cleaning-preview"
        type="info"
        :closable="false"
        :title="`Preview delta: ${cleaningPreview.row_count_delta} rows, ${cleaningPreview.column_count_delta} columns`"
      />
      <div v-if="cleaningPreview" class="preview-compare">
        <div>
          <h3>Before</h3>
          <el-table :data="cleaningPreview.before.rows" size="small" max-height="220">
            <el-table-column
              v-for="column in cleaningPreview.before.columns"
              :key="column"
              :label="column"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ formatCell(row[column]) }}</template>
            </el-table-column>
          </el-table>
        </div>
        <div>
          <h3>After</h3>
          <el-table :data="cleaningPreview.after.rows" size="small" max-height="220">
            <el-table-column
              v-for="column in cleaningPreview.after.columns"
              :key="column"
              :label="column"
              min-width="140"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ formatCell(row[column]) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { UploadFile } from 'element-plus'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import {
  getDatasetProfile,
  getDatasetPreview,
  getCleaningPlan,
  getLlmConfig,
  getLlmHealth,
  createImportDatasetJob,
  createCleaningJob,
  getJob,
  listDatasets,
  previewCleaning,
  type CleaningPlan,
  type CleaningPreview,
  type DatasetMetadata,
  type DatasetPreview,
  type JobRecord,
  type ProfileReport
} from '../../api/datasetApi'

type LlmConfig = {
  provider: string
  base_url: string
  model: string
  api_key_configured: boolean
}

type LlmHealth = {
  status: 'ok' | 'error'
  provider: string
  base_url: string
  model: string
  api_key_configured: boolean
  latency_ms: number
  sample: string
  error: string
}

const isUploading = ref(false)
const uploadError = ref('')
const successMessage = ref('')
const lastImport = ref<DatasetMetadata | null>(null)
const imports = ref<DatasetMetadata[]>([])
const activeJob = ref<JobRecord<DatasetMetadata> | null>(null)
const profile = ref<ProfileReport | null>(null)
const preview = ref<DatasetPreview | null>(null)
const cleaningPlan = ref<CleaningPlan | null>(null)
const cleaningPreview = ref<CleaningPreview | null>(null)
const selectedCleaningOperationIds = ref<string[]>([])
const llmConfig = ref<LlmConfig | null>(null)
const llmHealth = ref<LlmHealth | null>(null)
const llmError = ref('')
const pipelineActiveStep = ref(0)
const isCleaning = ref(false)
const isTestingLlm = ref(false)

const shortId = (id: string) => `${id.slice(0, 8)}...${id.slice(-6)}`
const formatCell = (value: unknown) => value == null ? 'NULL' : String(value)
const sleep = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))
const pipelineSteps = ['Import', 'Parquet', 'Profile', 'Dashboard']
const pipelineProgress = computed(() => {
  const completed = Math.min(pipelineActiveStep.value, pipelineSteps.length - 1)
  return `${(completed / (pipelineSteps.length - 1)) * 78}%`
})
const jobStatusTitle = computed(() => {
  if (!activeJob.value) {
    return ''
  }
  const label = activeJob.value.job_type === 'clean_dataset_version' ? 'Cleaning' : 'Import'
  if (activeJob.value.status === 'failed') {
    return `${label} job failed: ${activeJob.value.error}`
  }
  return `${label} job ${shortId(activeJob.value.job_id)} is ${activeJob.value.status}.`
})
const percent = (value: number) => `${Math.round(value * 100)}%`
const qualityTagType = (severity?: string) => {
  if (severity === 'high') {
    return 'danger'
  }
  if (severity === 'medium') {
    return 'warning'
  }
  return 'info'
}
const issueLabel = (issue: ProfileReport['quality_issues'][number]) => {
  const scope = issue.column ?? 'Dataset'
  return `${scope}: ${issue.type}${issue.count ? ` (${issue.count})` : ''}`
}

const loadDatasetArtifacts = async (dataset: DatasetMetadata) => {
  profile.value = await getDatasetProfile(dataset.dataset_id, dataset.version_id)
  try {
    const [previewResult, cleaningPlanResult] = await Promise.all([
      getDatasetPreview(dataset.dataset_id, dataset.version_id),
      getCleaningPlan(dataset.dataset_id, dataset.version_id)
    ])
    preview.value = previewResult
    cleaningPlan.value = cleaningPlanResult
    selectedCleaningOperationIds.value = cleaningPlanResult.operations.map(operation => operation.id)
  } catch (error) {
    preview.value = null
    cleaningPlan.value = null
    selectedCleaningOperationIds.value = []
    uploadError.value = error instanceof Error ? error.message : 'Dataset artifact loading failed'
  }
  cleaningPreview.value = null
}

const testLlmConnection = async () => {
  if (isTestingLlm.value) {
    return
  }

  isTestingLlm.value = true
  try {
    llmHealth.value = await getLlmHealth()
    if (llmHealth.value.status === 'ok') {
      ElMessage.success(`LLM connection ok in ${llmHealth.value.latency_ms} ms.`)
    } else {
      ElMessage.error(llmHealth.value.error || 'LLM health check failed')
    }
  } catch (error) {
    llmHealth.value = null
    ElMessage.error(error instanceof Error ? error.message : 'LLM health check failed')
  } finally {
    isTestingLlm.value = false
  }
}

const toggleCleaningOperation = (operationId: string) => {
  if (selectedCleaningOperationIds.value.includes(operationId)) {
    selectedCleaningOperationIds.value = selectedCleaningOperationIds.value.filter(id => id !== operationId)
    return
  }

  selectedCleaningOperationIds.value = [...selectedCleaningOperationIds.value, operationId]
}

const loadLlmConfig = async () => {
  llmError.value = ''
  try {
    llmConfig.value = await getLlmConfig()
  } catch (error) {
    llmConfig.value = null
    llmError.value = error instanceof Error ? error.message : 'LLM config loading failed'
  }
}

const handleFile = async (uploadFile: UploadFile) => {
  if (!uploadFile.raw) {
    return
  }

  isUploading.value = true
  uploadError.value = ''
  successMessage.value = ''
  profile.value = null
  preview.value = null
  cleaningPlan.value = null
  cleaningPreview.value = null
  activeJob.value = null
  pipelineActiveStep.value = 1

  try {
    const job = await createImportDatasetJob(uploadFile.raw)
    activeJob.value = job
    const completedJob = await waitForDatasetJob(job.job_id)
    if (completedJob.status === 'failed' || !completedJob.result) {
      throw new Error(completedJob.error || 'Import job failed')
    }
    const result = completedJob.result
    lastImport.value = result
    imports.value = [result, ...imports.value.filter(item => item.dataset_id !== result.dataset_id)].slice(0, 8)
    pipelineActiveStep.value = result.profile_status === 'ready' ? 3 : 2
    await loadDatasetArtifacts(result)
    pipelineActiveStep.value = result.dashboard_status === 'ready' ? 4 : 3
    successMessage.value = `Imported ${uploadFile.raw.name} and converted it to Parquet.`
    ElMessage.success(successMessage.value)
  } catch (error) {
    uploadError.value = error instanceof Error ? error.message : 'Import failed'
    ElMessage.error(uploadError.value)
  } finally {
    isUploading.value = false
  }
}

const waitForDatasetJob = async (jobId: string) => {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const job = await getJob<DatasetMetadata>(jobId)
    activeJob.value = job
    if (job.status === 'succeeded' || job.status === 'failed') {
      return job
    }
    await sleep(1000)
  }
  throw new Error('Import job timed out')
}

const loadCleaningPreview = async () => {
  if (!lastImport.value) {
    return
  }
  cleaningPreview.value = await previewCleaning(
    lastImport.value.dataset_id,
    lastImport.value.version_id,
    selectedCleaningOperationIds.value
  )
}

const executeCleaningPlan = async () => {
  if (!lastImport.value || isCleaning.value) {
    return
  }

  isCleaning.value = true
  uploadError.value = ''
  successMessage.value = ''
  activeJob.value = null
  try {
    const job = await createCleaningJob(
      lastImport.value.dataset_id,
      lastImport.value.version_id,
      selectedCleaningOperationIds.value
    )
    activeJob.value = job
    const completedJob = await waitForDatasetJob(job.job_id)
    if (completedJob.status === 'failed' || !completedJob.result) {
      throw new Error(completedJob.error || 'Cleaning job failed')
    }
    const result = completedJob.result
    lastImport.value = result
    imports.value = [result, ...imports.value.filter(item => item.version_id !== result.version_id)].slice(0, 8)
    await loadDatasetArtifacts(result)
    successMessage.value = `Created cleaned version ${result.version_id}.`
    ElMessage.success(successMessage.value)
  } catch (error) {
    uploadError.value = error instanceof Error ? error.message : 'Cleaning failed'
    ElMessage.error(uploadError.value)
  } finally {
    isCleaning.value = false
  }
}

onMounted(async () => {
  await loadLlmConfig()
  try {
    const datasets = await listDatasets()
    imports.value = datasets.slice(0, 8)
    lastImport.value = datasets[0] ?? null
    if (lastImport.value) {
      await loadDatasetArtifacts(lastImport.value)
      pipelineActiveStep.value = lastImport.value.dashboard_status === 'ready' ? 4 : 3
    }
  } catch (error) {
    uploadError.value = error instanceof Error ? error.message : 'Dataset list loading failed'
  }
})
</script>

<style scoped>
.status-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(300px, 0.8fr);
  gap: 14px;
  margin-bottom: 14px;
}

.status-alert {
  margin-bottom: 14px;
}

.llm-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.llm-heading h2 {
  margin-bottom: 0;
}

.health-detail {
  margin-left: 8px;
  color: var(--tr-text-muted);
  font-size: 12px;
}

.online-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--tr-green);
  font-weight: 700;
}

.online-status i {
  width: 8px;
  height: 8px;
  background: var(--tr-green);
  border-radius: 999px;
  box-shadow: 0 0 0 4px rgba(5, 150, 105, 0.12);
}

.session-label {
  color: var(--tr-text-muted);
  font-size: 12px;
}

.import-history {
  margin-bottom: 14px;
}

.profile-panel {
  margin-top: 14px;
}

.pipeline-steps {
  --pipeline-progress: 0%;
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 10px 4px 2px;
}

.pipeline-steps::before,
.pipeline-steps::after {
  position: absolute;
  top: 26px;
  right: 11%;
  left: 11%;
  height: 3px;
  content: "";
  border-radius: 999px;
}

.pipeline-steps::before {
  background: var(--tr-border);
}

.pipeline-steps::after {
  width: var(--pipeline-progress);
  max-width: 78%;
  background: var(--tr-blue);
  box-shadow: 0 0 18px rgba(37, 99, 235, 0.2);
}

.pipeline-step {
  position: relative;
  z-index: 1;
  display: grid;
  justify-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--tr-text-muted);
  font-size: 12px;
  font-weight: 800;
}

.step-badge {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  color: var(--tr-text-muted);
  background: #f9fafb;
  border: 1px solid var(--tr-border-strong);
  border-radius: 999px;
  box-shadow: var(--tr-shadow);
  transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
}

.pipeline-step.completed {
  color: var(--tr-blue);
}

.pipeline-step.completed .step-badge {
  color: #ffffff;
  background: var(--tr-blue);
  border-color: var(--tr-blue);
}

.pipeline-step.active .step-badge {
  color: var(--tr-blue);
  background: var(--tr-blue-soft);
  border-color: #93c5fd;
  animation: pipeline-pulse 1.6s ease-in-out infinite;
}

.step-title {
  overflow-wrap: anywhere;
  text-align: center;
}

@keyframes pipeline-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.24);
    transform: translateY(0);
  }

  50% {
    box-shadow: 0 0 0 8px rgba(37, 99, 235, 0);
    transform: translateY(-1px);
  }
}

.quality-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.data-preview-panel,
.cleaning-panel {
  margin-top: 14px;
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.panel-heading h2 {
  margin-bottom: 4px;
}

.panel-heading p,
.panel-heading span {
  margin: 0;
  color: var(--tr-text-muted);
  font-size: 13px;
}

.cleaning-actions {
  display: flex;
  gap: 8px;
}

.cleaning-preview {
  margin-top: 14px;
}

.preview-compare {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 14px;
}

.preview-compare h3 {
  margin: 0 0 8px;
  color: var(--tr-text);
  font-size: 14px;
}

h2 {
  margin: 0 0 16px;
  font-size: 16px;
}

code {
  padding: 2px 5px;
  color: #1d4ed8;
  background: var(--tr-blue-soft);
  border-radius: 4px;
}

@media (max-width: 900px) {
  .status-grid {
    grid-template-columns: 1fr;
  }

  .preview-compare {
    grid-template-columns: 1fr;
  }
}
</style>
