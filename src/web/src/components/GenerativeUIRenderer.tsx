import { useGenerativeUIDispatch } from '../catalog/GenerativeUIContext'
import { catalog } from '../catalog'
import type { GenerativeUIEnvelope } from '../catalog/types'

interface GenerativeUIRendererProps {
  envelope: GenerativeUIEnvelope
}

export function GenerativeUIRenderer({ envelope }: GenerativeUIRendererProps) {
  const { dispatch } = useGenerativeUIDispatch()
  return catalog.render(envelope, dispatch)
}
