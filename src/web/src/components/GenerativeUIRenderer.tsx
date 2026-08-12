import { DataTable } from './ui/DataTable'
import { MarkdownCard } from './ui/MarkdownCard'
import {
  isDataTable,
  isMarkdownCard,
  type GenerativeUIMetadata,
} from '../types/generative-ui'

interface GenerativeUIRendererProps {
  metadata: unknown
}

export function GenerativeUIRenderer({ metadata }: GenerativeUIRendererProps) {
  if (!metadata || typeof metadata !== 'object') {
    return null
  }

  const meta = metadata as GenerativeUIMetadata

  if (!meta.type) {
    console.warn('[GenerativeUIRenderer] generative_ui metadata 缺少 type 字段')
    return null
  }

  if (isMarkdownCard(meta)) {
    return <MarkdownCard metadata={meta} />
  }

  if (isDataTable(meta)) {
    return <DataTable metadata={meta} />
  }

  console.warn('[GenerativeUIRenderer] 不支持的 generative_ui type:', meta.type)
  return null
}
