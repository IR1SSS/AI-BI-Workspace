<template>
  <article class="dashboard-card" :class="[card.type, sizeClass]">
    <button
      v-if="canShowSql"
      class="sql-toggle"
      type="button"
      :aria-expanded="isSqlOpen"
      aria-label="Show chart SQL"
      title="Show chart SQL"
      @click="isSqlOpen = !isSqlOpen"
    >
      SQL
    </button>
    <div v-if="canShowSql && isSqlOpen" class="sql-popover" role="dialog" aria-label="Chart SQL">
      <pre>{{ sqlText }}</pre>
    </div>
    <span class="card-type">{{ card.type }}</span>
    <h3>{{ card.title }}</h3>
    <strong v-if="card.type === 'metric'">{{ compactMetric }}</strong>
    <ul v-else-if="card.type === 'text'" class="text-list">
      <li v-for="item in card.items ?? []" :key="item.title">
        <b>{{ item.title }}</b>
        <span>{{ item.body }}</span>
      </li>
    </ul>
    <template v-else>
      <div v-if="hasData" ref="chartElement" class="chart-surface" />
      <p v-else class="empty-chart">No chart data available</p>
    </template>
  </article>
</template>

<script setup lang="ts">
import {
  BarChart,
  BoxplotChart,
  HeatmapChart,
  LineChart,
  PieChart,
  ScatterChart,
  TreemapChart
} from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { init, use, type ECharts, type EChartsCoreOption } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { DashboardDraft } from '../../api/datasetApi'

type Card = DashboardDraft['cards'][number]

use([
  BarChart,
  BoxplotChart,
  HeatmapChart,
  LineChart,
  PieChart,
  ScatterChart,
  TreemapChart,
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer
])

const props = defineProps<{ card: Card }>()

const chartElement = ref<HTMLDivElement | null>(null)
const isSqlOpen = ref(false)
let chart: ECharts | null = null

const hasData = computed(() => Boolean(props.card.data && props.card.data.length > 0))
const sqlText = computed(() => props.card.sql?.trim() ?? '')
const canShowSql = computed(() => props.card.type === 'chart' && sqlText.value.length > 0)

const compactNumber = (value: number | string | undefined) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return String(value ?? '')
  }
  const abs = Math.abs(numeric)
  if (abs >= 100_000_000) {
    return `${Number((numeric / 100_000_000).toFixed(1))}亿`
  }
  if (abs >= 10_000) {
    return `${Number((numeric / 10_000).toFixed(1))}万`
  }
  if (abs >= 1_000) {
    return `${Number((numeric / 1_000).toFixed(1))}k`
  }
  return Number(numeric.toFixed(2)).toString()
}

const compactMetric = computed(() => compactNumber(props.card.value))
const sizeClass = computed(() => props.card.type === 'chart' ? `size-${props.card.layout?.size ?? 'standard'}` : '')

const truncateLabel = (value: string | number | undefined, maxLength = 8) => {
  const text = String(value ?? '')
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text
}

const labelFormatter = (maxLength = 8) => (value: string | number) => truncateLabel(value, maxLength)

const buildOption = (): EChartsCoreOption => {
  if (props.card.echarts_option && Array.isArray((props.card.echarts_option as any).series)) {
    return props.card.echarts_option as EChartsCoreOption
  }

  const data = props.card.data ?? []
  if (props.card.chart_type === 'pie') {
    return {
      color: ['#2f6fed', '#8cc152', '#f6b44b', '#e66a6a', '#52b6c8', '#7c6ad9'],
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'pie',
          radius: ['38%', '68%'],
          data: data.map(item => ({ name: item.label, value: item.value })),
          label: { overflow: 'truncate', width: 88, formatter: (params: any) => truncateLabel(params.name, 8) }
        }
      ]
    }
  }

  if (props.card.chart_type === 'scatter') {
    return {
      color: ['#2f6fed'],
      grid: { left: 10, right: 14, top: 18, bottom: 34, containLabel: true },
      tooltip: { trigger: 'item' },
      xAxis: { type: 'value', axisLabel: { formatter: compactNumber } },
      yAxis: { type: 'value', axisLabel: { formatter: compactNumber } },
      series: [
        {
          type: 'scatter',
          symbolSize: 8,
          data: data.map(item => [item.x, item.y])
        }
      ]
    }
  }

  if (props.card.chart_type === 'heatmap') {
    const heatmapPoints = data
      .map(item => {
        const fallbackParts = String(item.label ?? '').split(' / ')
        return {
          xLabel: String(item.xLabel ?? fallbackParts[0] ?? ''),
          yLabel: String(item.yLabel ?? fallbackParts[1] ?? ''),
          value: Number(item.value ?? 0)
        }
      })
      .filter(item => item.xLabel && item.yLabel && Number.isFinite(item.value))
    const xLabels = Array.from(new Set(heatmapPoints.map(item => item.xLabel)))
    const yLabels = Array.from(new Set(heatmapPoints.map(item => item.yLabel)))
    const values = heatmapPoints.map(item => item.value)
    const minValue = Math.min(...values, 0)
    const maxValue = Math.max(...values, 1)
    return {
      color: ['#2563eb'],
      grid: { left: 14, right: 22, top: 18, bottom: 62, containLabel: true },
      tooltip: {
        position: 'top',
        formatter: (params: any) => {
          const [xIndex, yIndex, value] = params.value
          return `${xLabels[xIndex]} / ${yLabels[yIndex]}: ${compactNumber(value)}`
        }
      },
      xAxis: {
        type: 'category',
        data: xLabels,
        splitArea: { show: true, areaStyle: { color: ['#ffffff', '#f8fafc'] } },
        axisLabel: {
          formatter: labelFormatter(7),
          hideOverlap: true,
          interval: 0,
          rotate: xLabels.some(label => label.length > 5) ? 28 : 0
        }
      },
      yAxis: {
        type: 'category',
        data: yLabels,
        splitArea: { show: true, areaStyle: { color: ['#ffffff', '#f8fafc'] } },
        axisLabel: { formatter: labelFormatter(7), hideOverlap: true }
      },
      visualMap: {
        min: minValue,
        max: maxValue,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        textStyle: { color: '#64748b', fontSize: 11 },
        itemHeight: 92,
        itemWidth: 9,
        inRange: { color: ['#eff6ff', '#bfdbfe', '#60a5fa', '#2563eb', '#3730a3'] }
      },
      series: [
        {
          type: 'heatmap',
          data: heatmapPoints.map(item => [
            xLabels.indexOf(item.xLabel),
            yLabels.indexOf(item.yLabel),
            item.value
          ]),
          itemStyle: {
            borderColor: '#ffffff',
            borderWidth: 2,
            borderRadius: 3
          },
          emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(20,36,54,.22)' } }
        }
      ]
    }
  }

  if (props.card.chart_type === 'treemap') {
    return {
      color: ['#2357c6', '#4f9f70', '#f0a33a', '#d95d5d', '#4aa8ba', '#7768c8'],
      tooltip: { trigger: 'item' },
      series: [
        {
          type: 'treemap',
          roam: false,
          breadcrumb: { show: false },
          label: { overflow: 'truncate' },
          upperLabel: { show: false },
          itemStyle: { borderColor: '#fff', borderWidth: 2, gapWidth: 2 },
          data: data.map(item => ({ name: item.label, value: item.value ?? 0 }))
        }
      ]
    }
  }

  if (props.card.chart_type === 'boxplot') {
    return {
      color: ['#2357c6'],
      grid: { left: 10, right: 16, top: 18, bottom: 34, containLabel: true },
      tooltip: { trigger: 'item' },
      xAxis: {
        type: 'category',
        data: data.map(item => item.label),
        boundaryGap: true,
        axisLabel: { formatter: labelFormatter(8), hideOverlap: true }
      },
      yAxis: { type: 'value', axisLabel: { formatter: compactNumber } },
      series: [
        {
          type: 'boxplot',
          data: data.map(item => [item.min, item.q1, item.median, item.q3, item.max])
        }
      ]
    }
  }

  if (props.card.chart_type === 'bullet') {
    const labels = data.map(item => item.label)
    const values = data.map(item => Number(item.value ?? 0))
    const targets = data.map(item => Number(item.target ?? item.marker ?? 0))
    return {
      color: ['#2357c6', '#d95d5d'],
      grid: { left: 10, right: 18, top: 18, bottom: 30, containLabel: true },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'value', axisLabel: { formatter: compactNumber } },
      yAxis: {
        type: 'category',
        data: labels,
        axisLabel: { formatter: labelFormatter(7), hideOverlap: true }
      },
      series: [
        {
          type: 'bar',
          data: values,
          barMaxWidth: 18,
          itemStyle: { borderRadius: [0, 4, 4, 0] }
        },
        {
          type: 'scatter',
          symbol: 'rect',
          symbolSize: [4, 24],
          data: targets.map((target, index) => [target, labels[index]]),
          tooltip: { valueFormatter: (value: number) => `Target ${value}` }
        }
      ]
    }
  }

  const labels = data.map(item => item.label)
  const values = data.map(item => item.value)
  const isLine = props.card.chart_type === 'line' || props.card.chart_type === 'area'
  return {
    color: ['#2f6fed'],
    grid: { left: 10, right: 14, top: 18, bottom: 48, containLabel: true },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: {
        interval: 0,
        formatter: labelFormatter(7),
        hideOverlap: true,
        rotate: labels.some(label => label.length > 5) ? 28 : 0
      }
    },
    yAxis: { type: 'value', axisLabel: { formatter: compactNumber } },
    series: [
      {
        type: isLine ? 'line' : 'bar',
        data: values,
        smooth: isLine,
        areaStyle: props.card.chart_type === 'area' ? { opacity: 0.18 } : undefined,
        barMaxWidth: 34,
        itemStyle: { borderRadius: [4, 4, 0, 0] }
      }
    ]
  }
}

const renderChart = async () => {
  if (props.card.type !== 'chart' || !chartElement.value || !hasData.value) {
    return
  }

  await nextTick()
  chart = chart ?? init(chartElement.value)
  chart.setOption(buildOption())
}

const resizeChart = () => {
  chart?.resize()
}

watch(() => props.card, renderChart, { deep: true })
watch(() => props.card.id, () => {
  isSqlOpen.value = false
})

onMounted(() => {
  renderChart()
  window.addEventListener('resize', resizeChart)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.dashboard-card {
  position: relative;
  min-height: 278px;
  padding: 16px;
  overflow: hidden;
  background: var(--tr-surface);
  border: 1px solid var(--tr-border);
  border-radius: 8px;
  box-shadow: var(--tr-shadow);
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.dashboard-card.chart:hover {
  border-color: #bfdbfe;
  box-shadow: var(--tr-shadow-lg);
  transform: translateY(-1px);
}

.sql-toggle {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  min-width: 38px;
  min-height: 24px;
  padding: 3px 7px;
  color: #1d4ed8;
  cursor: pointer;
  background: var(--tr-blue-soft);
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0;
}

.sql-toggle:hover,
.sql-toggle[aria-expanded="true"] {
  color: #ffffff;
  background: var(--tr-blue);
  border-color: var(--tr-blue);
}

.sql-popover {
  position: absolute;
  top: 42px;
  right: 12px;
  z-index: 5;
  width: min(420px, calc(100% - 24px));
  max-height: 190px;
  overflow: auto;
  padding: 10px;
  background: #122033;
  border: 1px solid #223854;
  border-radius: 6px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.24);
}

.sql-popover pre {
  margin: 0;
  color: #d7e8ff;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.dashboard-card.metric {
  min-height: 84px;
  padding: 14px;
  background: var(--tr-surface);
}

.dashboard-card.chart {
  border-color: var(--tr-border);
}

.dashboard-card.text {
  min-height: 220px;
}

.dashboard-card.chart.size-compact {
  min-height: 238px;
}

.dashboard-card.chart.size-wide,
.dashboard-card.chart.size-hero {
  grid-column: span 2;
}

.dashboard-card.chart.size-tall {
  grid-row: span 2;
  min-height: 520px;
}

.dashboard-card.chart.size-hero {
  min-height: 360px;
}

.dashboard-card.chart.size-tall .chart-surface {
  height: 448px;
}

.dashboard-card.chart.size-hero .chart-surface {
  height: 286px;
}

.dashboard-card h3 {
  margin: 8px 0 12px;
  color: var(--tr-text);
  font-size: 15px;
  font-weight: 700;
  line-height: 1.35;
}

.dashboard-card strong {
  color: var(--tr-text);
  font-size: 30px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}

.dashboard-card.metric h3 {
  margin: 6px 0 5px;
  color: var(--tr-text-muted);
  font-size: 11px;
  font-weight: 600;
  line-height: 1.25;
}

.dashboard-card.metric strong {
  font-size: 24px;
  line-height: 1.1;
}

.card-type {
  color: var(--tr-text-soft);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.dashboard-card.metric .card-type {
  display: none;
}

.chart-surface {
  width: 100%;
  height: 210px;
}

.empty-chart {
  margin: 18px 0 0;
  color: var(--tr-text-muted);
}

.text-list {
  display: grid;
  gap: 10px;
  padding: 0;
  margin: 0;
  list-style: none;
}

.text-list li {
  display: grid;
  gap: 3px;
  padding-top: 8px;
  border-top: 1px solid var(--tr-border);
}

.text-list b {
  font-size: 13px;
}

.text-list span {
  color: #4f5f72;
  font-size: 13px;
  line-height: 1.45;
}
</style>
