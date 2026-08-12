import { render, renderHook, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RenderMessageProps } from '@copilotkit/react-ui'
import {
  extractGenerativeUIMetadata,
  SAMPLE_DATA_TABLE,
  SAMPLE_MARKDOWN_CARD,
  useGenerativeUI,
} from '../useGenerativeUI'

function createRenderMessageProps(message: unknown): RenderMessageProps {
  return {
    message: message as RenderMessageProps['message'],
    messages: [],
    inProgress: false,
    index: 0,
    isCurrentMessage: true,
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

  it('extracts generative_ui metadata from message', () => {
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
  it('renderMessage returns GenerativeUIRenderer when metadata is present', () => {
    const { result } = renderHook(() => useGenerativeUI())
    const metadata = {
      type: 'markdown_card' as const,
      title: 'Mock Card',
      content: 'Mock content',
    }
    const message = { id: 'msg-1', metadata: { generative_ui: metadata } }

    const element = result.current.renderMessage(createRenderMessageProps(message))

    expect(element).toBeDefined()
    render(element!)
    expect(screen.getByText('Mock Card')).toBeInTheDocument()
    expect(screen.getByText('Mock content')).toBeInTheDocument()
  })

  it('renderMessage returns undefined when metadata is absent and no mock is configured', () => {
    const { result } = renderHook(() => useGenerativeUI())
    const message = { id: 'msg-1', content: 'hello' }

    const element = result.current.renderMessage(createRenderMessageProps(message))

    expect(element).toBeUndefined()
  })

  it('renderMessage falls back to mock metadata when no real metadata exists', () => {
    const { result } = renderHook(() => useGenerativeUI({ mockMetadata: SAMPLE_MARKDOWN_CARD }))
    const message = { id: 'msg-1', content: 'hello' }

    const element = result.current.renderMessage(createRenderMessageProps(message))

    expect(element).toBeDefined()
    render(element!)
    expect(screen.getByText(SAMPLE_MARKDOWN_CARD.title!)).toBeInTheDocument()
    expect(screen.getByText(/Markdown/)).toBeInTheDocument()
  })

  it('renderMessage prefers real metadata over mock metadata', () => {
    const { result } = renderHook(() => useGenerativeUI({ mockMetadata: SAMPLE_MARKDOWN_CARD }))
    const message = { id: 'msg-1', metadata: { generative_ui: SAMPLE_DATA_TABLE } }

    const element = result.current.renderMessage(createRenderMessageProps(message))

    expect(element).toBeDefined()
    render(element!)
    expect(screen.getByText(SAMPLE_DATA_TABLE.title!)).toBeInTheDocument()
    expect(screen.getByText('A')).toBeInTheDocument()
  })
})
