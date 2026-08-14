import type { ReactNode } from 'react'
import type { ZodType } from 'zod'

export interface GenerativeUIEnvelope<TProps = unknown> {
  type: string
  props?: TProps
  surfaceId?: string
}

export interface CatalogComponentDefinition<TProps = unknown> {
  /** 组件的人类可读描述，可用于注入系统提示词。 */
  description: string
  /** Zod schema，用于运行时校验 props 并生成 JSON Schema。 */
  schema: ZodType<TProps>
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface CatalogRenderContext<TProps = any> {
  props: TProps
  surfaceId?: string
  /** 将用户动作发回 Agent 的回调。 */
  dispatch: (action: unknown) => void
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type CatalogRenderer<TProps = any> = (ctx: CatalogRenderContext<TProps>) => ReactNode

export interface JSONSchema {
  type?: string
  description?: string
  properties?: Record<string, JSONSchema>
  required?: string[]
  items?: JSONSchema
  additionalProperties?: JSONSchema | boolean
  enum?: string[]
}
