import { useRenderTool } from '@copilotkit/react-core/v2'
import { z } from 'zod'
import { GenerativeUIRenderer } from '../components/GenerativeUIRenderer'
import type { GenerativeUIEnvelope } from '../catalog/types'

const renderUiParameters = z.object({
  type: z.string(),
  props: z.record(z.unknown()).optional(),
  surface_id: z.string().optional(),
})

export function parseEnvelope(result: unknown): GenerativeUIEnvelope | undefined {
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch {
      return undefined
    }
  }

  if (!result || typeof result !== 'object') {
    return undefined
  }

  let payload = result as Record<string, unknown>

  if ('generative_ui' in payload && payload.generative_ui && typeof payload.generative_ui === 'object') {
    payload = payload.generative_ui as Record<string, unknown>
  }

  if (typeof payload.type !== 'string') {
    return undefined
  }

  return {
    type: payload.type,
    props: payload.props,
    surfaceId: typeof payload.surfaceId === 'string' ? payload.surfaceId : undefined,
  }
}

export function useGenerativeUITool() {
  useRenderTool(
    {
      name: 'render_ui',
      parameters: renderUiParameters,
      render: ({ status, result }) => {
        if (status === 'executing' || status === 'inProgress') {
          return (
            <div className="my-2 text-sm text-gray-500">正在渲染界面组件...</div>
          )
        }

        if (status !== 'complete') {
          return <></>
        }

        const envelope = parseEnvelope(result)
        if (!envelope) {
          console.warn('[useGenerativeUITool] 无法解析 envelope:', {
            typeof: typeof result,
            result,
            parsed: typeof result === 'object' && result !== null ? Object.keys(result as object) : null,
          })
          return <></>
        }

        return <GenerativeUIRenderer envelope={envelope} />
      },
    },
    [],
  )
}
