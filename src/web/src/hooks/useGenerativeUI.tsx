import { useCallback } from 'react'
import type { RenderMessageProps } from '@copilotkit/react-ui'
import { GenerativeUIRenderer } from '../components/GenerativeUIRenderer'
import type {
  DataTableMetadata,
  GenerativeUIMetadata,
  MarkdownCardMetadata,
} from '../types/generative-ui'

export const SAMPLE_MARKDOWN_CARD: MarkdownCardMetadata = {
  type: 'markdown_card',
  title: 'Generative UI 示例',
  content: '这是 **Markdown** 卡片示例，用于验证 CopilotKit 消息流中的 Generative UI 渲染。',
}

export const SAMPLE_DATA_TABLE: DataTableMetadata = {
  type: 'data_table',
  title: '示例数据表',
  columns: [
    { key: 'name', label: '名称' },
    { key: 'value', label: '数值' },
  ],
  rows: [
    { name: 'A', value: 100 },
    { name: 'B', value: 200 },
  ],
}

export function extractGenerativeUIMetadata(message: unknown): GenerativeUIMetadata | undefined {
  if (!message || typeof message !== 'object') {
    return undefined
  }

  const msg = message as Record<string, unknown>
  const metadata = msg.metadata

  if (!metadata || typeof metadata !== 'object') {
    return undefined
  }

  const meta = metadata as Record<string, unknown>
  const generativeUI = meta.generative_ui

  if (!generativeUI || typeof generativeUI !== 'object') {
    return undefined
  }

  return generativeUI as GenerativeUIMetadata
}

interface UseGenerativeUIOptions {
  mockMetadata?: GenerativeUIMetadata
}

export function useGenerativeUI(options: UseGenerativeUIOptions = {}) {
  const { mockMetadata } = options

  const renderMessage = useCallback(
    (props: RenderMessageProps) => {
      const metadata = extractGenerativeUIMetadata(props.message) ?? mockMetadata

      if (metadata) {
        return <GenerativeUIRenderer metadata={metadata} />
      }

      return undefined
    },
    [mockMetadata],
  )

  return { renderMessage }
}
