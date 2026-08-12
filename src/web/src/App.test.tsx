import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { RenderMessageProps } from '@copilotkit/react-ui'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const copilotKitMock = vi.fn()
const copilotSidebarMock = vi.fn()
const copilotChatMock = vi.fn()

vi.mock('@copilotkit/react-core', () => ({
  CopilotKit: (props: React.PropsWithChildren<{ runtimeUrl: string; threadId: string }>) => {
    copilotKitMock(props)
    return <div data-testid="copilot-kit">{props.children}</div>
  },
}))

vi.mock('@copilotkit/react-ui', () => ({
  CopilotSidebar: (props: React.PropsWithChildren<{ defaultOpen: boolean; clickOutsideToClose: boolean; className: string }>) => {
    copilotSidebarMock(props)
    return <div data-testid="copilot-sidebar">{props.children}</div>
  },
  CopilotChat: (props: { className: string; labels: Record<string, string>; RenderMessage?: React.ComponentType<RenderMessageProps> }) => {
    copilotChatMock(props)
    return <div data-testid="copilot-chat">{props.labels.title}</div>
  },
}))

const mockFetch = vi.fn()

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders CopilotKit with default runtime url', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ agents: [{ name: 'default' }, { name: 'code_reviewer' }] }),
    })

    render(<App />)

    await waitFor(() => expect(screen.getByTestId('copilot-kit')).toBeInTheDocument())

    expect(copilotKitMock).toHaveBeenCalledWith(
      expect.objectContaining({
        runtimeUrl: '/agent',
        threadId: expect.stringMatching(/^thread-/),
      }),
    )
    expect(copilotSidebarMock).toHaveBeenCalledWith(
      expect.objectContaining({
        defaultOpen: true,
        clickOutsideToClose: false,
        className: 'h-full',
      }),
    )
    expect(copilotChatMock).toHaveBeenCalledWith(
      expect.objectContaining({
        className: 'h-full',
        labels: {
          title: 'DeepAgents Chat',
          initial: '有什么可以帮你的？',
          placeholder: '输入消息...',
        },
        RenderMessage: expect.any(Function),
      }),
    )
  })

  it('updates runtime url when agent changes', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ agents: [{ name: 'default' }, { name: 'code_reviewer' }] }),
    })

    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument())

    await user.selectOptions(screen.getByRole('combobox'), 'code_reviewer')

    await waitFor(() =>
      expect(copilotKitMock).toHaveBeenLastCalledWith(
        expect.objectContaining({
          runtimeUrl: '/agent/code_reviewer',
        }),
      ),
    )
  })
})
