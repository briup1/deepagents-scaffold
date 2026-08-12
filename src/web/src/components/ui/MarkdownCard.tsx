import type { MarkdownCardMetadata } from '../../types/generative-ui'

interface MarkdownCardProps {
  metadata: MarkdownCardMetadata
}

export function MarkdownCard({ metadata }: MarkdownCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm my-2">
      {metadata.title && (
        <h3 className="mb-2 text-sm font-semibold text-gray-700">{metadata.title}</h3>
      )}
      <div className="prose prose-sm max-w-none">
        <pre className="whitespace-pre-wrap text-sm text-gray-800">{metadata.content}</pre>
      </div>
    </div>
  )
}
