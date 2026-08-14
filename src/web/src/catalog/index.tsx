import { z } from 'zod'
import { ButtonGroup } from '../components/ui/ButtonGroup'
import { Chart } from '../components/ui/Chart'
import { DataTable } from '../components/ui/DataTable'
import { Form } from '../components/ui/Form'
import { MarkdownCard } from '../components/ui/MarkdownCard'
import { MetricCard } from '../components/ui/MetricCard'
import { createCatalog } from './createCatalog'

const markdownCardSchema = z.object({
  title: z.string().optional(),
  content: z.string(),
})

const dataTableSchema = z.object({
  title: z.string().optional(),
  columns: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
    }),
  ),
  rows: z.array(z.record(z.union([z.string(), z.number(), z.boolean()]))),
})

const formFieldSchema = z.object({
  name: z.string(),
  label: z.string(),
  type: z.enum(['text', 'number']).optional(),
})

const formSchema = z.object({
  title: z.string().optional(),
  fields: z.array(formFieldSchema),
  submitLabel: z.string().optional(),
})

const buttonGroupSchema = z.object({
  title: z.string().optional(),
  buttons: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
    }),
  ),
})

const metricCardSchema = z.object({
  title: z.string().optional(),
  value: z.number(),
  unit: z.string().optional(),
  change: z.number().optional(),
})

const chartSchema = z.object({
  title: z.string().optional(),
  kind: z.enum(['bar', 'line']),
  data: z.array(
    z.object({
      label: z.string(),
      value: z.number(),
    }),
  ),
  width: z.number().optional(),
  height: z.number().optional(),
})

export const catalog = createCatalog(
  {
    markdown_card: {
      description: '渲染带有标题的 Markdown 文本卡片。',
      schema: markdownCardSchema,
    },
    data_table: {
      description: '按列和行渲染结构化数据表。',
      schema: dataTableSchema,
    },
    form: {
      description: '渲染可提交的表单，用户提交后 Agent 会收到 form_submit 动作。',
      schema: formSchema,
    },
    button_group: {
      description: '渲染一组按钮，点击后 Agent 会收到 button_click 动作。',
      schema: buttonGroupSchema,
    },
    metric_card: {
      description: '渲染单个指标数值与可选变化率。',
      schema: metricCardSchema,
    },
    chart: {
      description: '渲染简单 SVG 柱状图或折线图。',
      schema: chartSchema,
    },
  },
  {
    markdown_card: ({ props }) => <MarkdownCard {...props} />,
    data_table: ({ props }) => <DataTable {...props} />,
    form: ({ props, dispatch, surfaceId }) => <Form {...props} dispatch={dispatch} surfaceId={surfaceId} />,
    button_group: ({ props, dispatch, surfaceId }) => <ButtonGroup {...props} dispatch={dispatch} surfaceId={surfaceId} />,
    metric_card: ({ props }) => <MetricCard {...props} />,
    chart: ({ props }) => <Chart {...props} />,
  },
)

/** 供后端系统提示词使用的组件 schema 描述。 */
export const componentSchema = catalog.schema
