import { render, renderHook, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { RenderMessageProps } from '@copilotkit/react-ui'
import {
  extractGenerativeUIMetadata,
  SAMPLE_DATA_TABLE,
  SAMPLE_MARKDOWN_CARD,
  useGenerativeUI,
} from '../useGenerativeUI'

const MockAssistantMessage = vi.fn(() => <div data-testid="default-assistant">Assistant</div>)
const MockUserMessage = vi.fn(() => <div data-testid="default-user">User</div>)

function createRenderMessageProps(message: unknown): RenderMessageProps {
  return {
    message: message as RenderMessageProps['message'],
    messages: [],
    inProgress: false,
    index: 0,
    isCurrentMessage: true,
    AssistantMessage: MockAssistantMessage,
    UserMessage: MockUserMessage,
  }
}

describe('extractGenerativeUIMetadata', () => {
  it('returns undefined for non-object messages', () => {
    expect(extractGenerativeUIMetadata(null)).toBeUndefined()
    expect(extractGenerativeUIMetadata(undefined)).toBeUndefined()
    expect(extractGenerativeUIMetadata('text')).toBeUndefined()
  })

  it('returns undefined when metadata is missing', () => {
    expect(extractGenerativeUIMetadata({ id: 'msg-1', content: 'hello' })).toBeUndefined()
  })

  it('returns undefined when generative_ui is missing', () => {
    expect(extractGenerativeUIMetadata({ id: 'msg-1', metadata: {} })).toBeUndefined()
  })

  it('returns undefined for unsupported generative_ui type', () => {
    expect(
      extractGenerativeUIMetadata({
        id: 'msg-1',
        metadata: { generative_ui: { type: 'unknown' } },
      }),
    ).toBeUndefined()
  })

  it('extracts markdown_card metadata from message', () => {
    const metadata = {
      type: 'markdown_card' as const,
      title: 'Card',
      content: 'Content',
    }
    const message = { id: 'msg-1', metadata: { generative_ui: metadata } }

    expect(extractGenerativeUIMetadata(message)).toEqual(metadata)
  })

  it('extracts data_table metadata from message', () => {
    const metadata = {
      type: 'data_table' as const,
      title: 'Table',
      columns: [{ key: 'k', label: 'K' }],
      rows: [{ k: 'v' }],
    }
    const message = { id: 'msg-1', metadata: { generative_ui: metadata } }

    expect(extractGenerativeUIMetadata(message)).toEqual(metadata)
  })
})

describe('useGenerativeUI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renderMessage returns GenerativeUIRenderer when metadata is present', () => {
    const { result } = renderHook(() => useGenerativeUI())
    const metadata = {
      type: 'markdown_card' as const,
      title: 'Mock Card',
      content: 'Mock content',
    }
    const message = { id: 'msg-1', role: 'assistant' as const, metadata: { generative_ui: metadata } }

    const element = result.current.renderMessage(createRenderMessageProps(message))

    expect(element).toBeDefined()
    render(element!)
    expect(screen.getByText('Mock Card')).toBeInTheDocument()
    expect(screen.getByText('Mock content')).toBeInTheDocument()
    expect(MockAssistantMessage).not.toHaveBeenCalled()
  })

  it('renderMessage returns default AssistantMessage for assistant messages without metadata', () => {
    const { result } = renderHook(() => useGenerativeUI())
    const message = { id: 'msg-1', role: 'assistant' as const, content: 'hello' }

    const element = result.current.renderMessage(createRenderMessageProps(message))

    expect(element).toBeDefined()
    render(element!)
    expect(screen.getByTestId('default-assistant')).toBeInTheDocument()
    expect(MockAssistantMessage).toHaveBeenCalledWith(
      expect.objectContaining({ message }),
      expect.anything(),
    )
  })

  it('renderMessage returns default UserMessage for user messages', () => {
    const { result } = renderHook(() => useGenerativeUI({ enableMock: true }))
    const message = { id: 'msg-1', role: 'user' as const, content: 'hello' }

    const element = result.current.renderMessage(createRenderMessageProps(message))

    expect(element).toBeDefined()
    render(element!)
    expect(screen.getByTestId('default-user')).toBeInTheDocument()
    expect(MockUserMessage).toHaveBeenCalled()
  })

  it('renderMessage falls back to mock metadata only for current assistant message', () => {
    const { result } = renderHook(() => useGenerativeUI({ enableMock: true, mockMetadata: SAMPLE_MARKDOWN_CARD }))
    const message = { id: 'msg-1', role: 'assistant' as const, content: 'hello' }

    const element = result.current.renderMessage(createRenderMessageProps(message))

    expect(element).toBeDefined()
    render(element!)
    expect(screen.getByText(SAMPLE_MARKDOWN_CARD.title!)).toBeInTheDocument()
    expect(MockAssistantMessage).not.toHaveBeenCalled()
  })

  it('renderMessage does not use mock for non-current assistant messages', () => {
    const { result } = renderHook(() => useGenerativeUI({ enableMock: true, mockMetadata: SAMPLE_MARKDOWN_CARD }))
    const message = { id: 'msg-1', role: 'assistant' as const, content: 'hello' }

    const element = result.current.renderMessage({
      ...createRenderMessageProps(message),
      isCurrentMessage: false,
    })

    expect(element).toBeDefined()
    render(element!)
    expect(screen.getByTestId('default-assistant')).toBeInTheDocument()
  })

  it('renderMessage prefers real metadata over mock metadata', () => {
    const { result } = renderHook(() => useGenerativeUI({ enableMock: true, mockMetadata: SAMPLE_MARKDOWN_CARD }))
    const message = {
      id: 'msg-1',
      role: 'assistant' as const,
      metadata: { generative_ui: SAMPLE_DATA_TABLE },
    }

    const element = result.current.renderMessage(createRenderMessageProps(message))

    expect(element).toBeDefined()
    render(element!)
    expect(screen.getByText(SAMPLE_DATA_TABLE.title!)).toBeInTheDocument()
    expect(screen.getByText('A')).toBeInTheDocument()
  })
})
