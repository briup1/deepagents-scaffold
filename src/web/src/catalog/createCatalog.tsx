import type { ReactNode } from 'react'
import type {
  ZodArray,
  ZodDefault,
  ZodEnum,
  ZodObject,
  ZodOptional,
  ZodRecord,
  ZodType,
} from 'zod'
import { ZodFirstPartyTypeKind } from 'zod'
import type {
  CatalogComponentDefinition,
  CatalogRenderContext,
  CatalogRenderer,
  GenerativeUIEnvelope,
  JSONSchema,
} from './types'

export interface Catalog<TDefinitions extends Record<string, CatalogComponentDefinition>> {
  definitions: TDefinitions
  renderers: Record<keyof TDefinitions, CatalogRenderer<any>>
  /** 每个注册组件的 JSON Schema 描述。 */
  schema: Record<string, JSONSchema>
  /** 根据 envelope 查找 renderer 并渲染，失败时降级。 */
  render: (envelope: GenerativeUIEnvelope, dispatch: (action: unknown) => void) => ReactNode
}

function zodToJsonSchema(schema: ZodType): JSONSchema {
  const def = (schema as unknown as { _def: { typeName: ZodFirstPartyTypeKind } })._def

  switch (def.typeName) {
    case ZodFirstPartyTypeKind.ZodString:
      return { type: 'string' }
    case ZodFirstPartyTypeKind.ZodNumber:
      return { type: 'number' }
    case ZodFirstPartyTypeKind.ZodBoolean:
      return { type: 'boolean' }
    case ZodFirstPartyTypeKind.ZodAny:
      return {}
    case ZodFirstPartyTypeKind.ZodOptional: {
      const inner = (def as unknown as ZodOptional<ZodType>['_def']).innerType
      return zodToJsonSchema(inner)
    }
    case ZodFirstPartyTypeKind.ZodDefault: {
      const inner = (def as unknown as ZodDefault<ZodType>['_def']).innerType
      return zodToJsonSchema(inner)
    }
    case ZodFirstPartyTypeKind.ZodArray: {
      const itemType = (def as unknown as ZodArray<ZodType>['_def']).type
      return { type: 'array', items: zodToJsonSchema(itemType) }
    }
    case ZodFirstPartyTypeKind.ZodRecord: {
      const valueType = (def as unknown as ZodRecord<ZodType>['_def']).valueType
      return { type: 'object', additionalProperties: zodToJsonSchema(valueType) }
    }
    case ZodFirstPartyTypeKind.ZodEnum: {
      const values = (def as unknown as ZodEnum<[string, ...string[]]>['_def']).values
      return { type: 'string', enum: [...values] }
    }
    case ZodFirstPartyTypeKind.ZodObject: {
      const shape = (def as unknown as ZodObject<Record<string, ZodType>>['_def']).shape()
      const properties: Record<string, JSONSchema> = {}
      const required: string[] = []
      for (const [key, value] of Object.entries(shape)) {
        properties[key] = zodToJsonSchema(value)
        const innerDef = (value as unknown as { _def: { typeName: ZodFirstPartyTypeKind } })._def
        if (
          innerDef.typeName !== ZodFirstPartyTypeKind.ZodOptional &&
          innerDef.typeName !== ZodFirstPartyTypeKind.ZodDefault
        ) {
          required.push(key)
        }
      }
      const result: JSONSchema = { type: 'object', properties }
      if (required.length > 0) {
        result.required = required
      }
      return result
    }
    default:
      return {}
  }
}

function extractSchemas<TDefinitions extends Record<string, CatalogComponentDefinition>>(
  definitions: TDefinitions,
): Record<string, JSONSchema> {
  const schemas: Record<string, JSONSchema> = {}
  for (const [type, definition] of Object.entries(definitions)) {
    schemas[type] = {
      description: definition.description,
      ...zodToJsonSchema(definition.schema),
    }
  }
  return schemas
}

function Fallback({
  envelope,
  error,
}: {
  envelope: GenerativeUIEnvelope
  error?: string
}) {
  return (
    <div className="my-2 rounded-lg border border-yellow-200 bg-yellow-50 p-4 text-sm text-yellow-800">
      <p className="font-medium">无法渲染 Generative UI</p>
      {error && <p className="mt-1 text-yellow-700">{error}</p>}
      <pre className="mt-2 max-h-40 overflow-auto rounded bg-white p-2 text-xs text-gray-700">
        {JSON.stringify(envelope, null, 2)}
      </pre>
    </div>
  )
}

export function createCatalog<TDefinitions extends Record<string, CatalogComponentDefinition>>(
  definitions: TDefinitions,
  renderers: { [K in keyof TDefinitions]: CatalogRenderer<any> },
): Catalog<TDefinitions> {
  return {
    definitions,
    renderers,
    schema: extractSchemas(definitions),
    render(envelope, dispatch) {
      const type = envelope.type
      const renderer = renderers[type as keyof TDefinitions] as
        | ((ctx: CatalogRenderContext) => ReactNode)
        | undefined
      const definition = definitions[type as keyof TDefinitions] as CatalogComponentDefinition | undefined

      if (!renderer || !definition) {
        console.warn(`[Catalog] 未注册的 Generative UI 类型: ${type}`)
        return <Fallback envelope={envelope} />
      }

      try {
        const parsed = definition.schema.parse(envelope.props ?? {})
        return renderer({ props: parsed as any, surfaceId: envelope.surfaceId, dispatch })
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        console.error(`[Catalog] 渲染 ${type} 时 props 校验失败:`, err)
        return <Fallback envelope={envelope} error={message} />
      }
    },
  }
}
