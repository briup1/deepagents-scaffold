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

  if (isMarkdownCard(meta)) {
    return <MarkdownCard metadata={meta} />
  }

  if (isDataTable(meta)) {
    return <DataTable metadata={meta} />
  }

  console.warn('[GenerativeUIRenderer] unsupported generative_ui type:', meta.type)
  return null
}
