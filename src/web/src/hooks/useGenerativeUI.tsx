import type { AIMessage, UserMessage } from '@copilotkit/shared'
import { useCallback } from 'react'
import type {
  AssistantMessageProps,
  RenderMessageProps,
  UserMessageProps,
} from '@copilotkit/react-ui'
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

const VALID_GENERATIVE_UI_TYPES = ['markdown_card', 'data_table'] as const

type ValidGenerativeUIType = (typeof VALID_GENERATIVE_UI_TYPES)[number]

function isValidGenerativeUIType(type: unknown): type is ValidGenerativeUIType {
  return typeof type === 'string' && VALID_GENERATIVE_UI_TYPES.includes(type as ValidGenerativeUIType)
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

  const ui = generativeUI as Record<string, unknown>

  if (!isValidGenerativeUIType(ui.type)) {
    return undefined
  }

  return generativeUI as GenerativeUIMetadata
}

interface UseGenerativeUIOptions {
  enableMock?: boolean
  mockMetadata?: GenerativeUIMetadata
}

function isAssistantMessage(message: RenderMessageProps['message']): message is AIMessage {
  return message.role === 'assistant'
}

function isUserMessage(message: RenderMessageProps['message']): message is UserMessage {
  return message.role === 'user'
}

export function useGenerativeUI(options: UseGenerativeUIOptions = {}) {
  const { enableMock = false, mockMetadata = SAMPLE_MARKDOWN_CARD } = options

  const renderMessage = useCallback(
    (props: RenderMessageProps) => {
      const { message } = props
      const realMetadata = extractGenerativeUIMetadata(message)

      // Mock 仅作用于当前 assistant 消息，避免影响用户消息与历史消息。
      const shouldUseMock =
        enableMock &&
        !realMetadata &&
        isAssistantMessage(message) &&
        props.isCurrentMessage

      const metadata = realMetadata ?? (shouldUseMock ? mockMetadata : undefined)

      if (metadata) {
        return <GenerativeUIRenderer metadata={metadata} />
      }

      return renderDefaultMessage(props)
    },
    [enableMock, mockMetadata],
  )

  return { renderMessage }
}

function renderDefaultMessage(props: RenderMessageProps) {
  const {
    message,
    messages,
    inProgress,
    index,
    isCurrentMessage,
    onRegenerate,
    onCopy,
    onThumbsUp,
    onThumbsDown,
    messageFeedback,
    markdownTagRenderers,
    AssistantMessage,
    UserMessage,
    ImageRenderer,
  } = props

  if (isUserMessage(message) && UserMessage) {
    const userProps: UserMessageProps = {
      rawData: message,
      message,
      ImageRenderer: ImageRenderer!,
    }
    return <UserMessage key={index} {...userProps} />
  }

  if (isAssistantMessage(message) && AssistantMessage) {
    const assistantProps: AssistantMessageProps = {
      rawData: message,
      message,
      messages,
      isLoading: inProgress && isCurrentMessage && !message.content,
      isGenerating: inProgress && isCurrentMessage && !!message.content,
      isCurrentMessage,
      onRegenerate: () => onRegenerate?.(message.id),
      onCopy,
      onThumbsUp,
      onThumbsDown,
      feedback: messageFeedback?.[message.id] ?? null,
      markdownTagRenderers,
      ImageRenderer,
    }
    return <AssistantMessage key={index} {...assistantProps} />
  }

  return null
}
