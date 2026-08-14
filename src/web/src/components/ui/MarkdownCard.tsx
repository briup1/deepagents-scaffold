interface MarkdownCardProps {
  title?: string
  content: string
}

export function MarkdownCard({ title, content }: MarkdownCardProps) {
  return (
    <div className="my-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      {title && (
        <h3 className="mb-2 text-sm font-semibold text-gray-700">{title}</h3>
      )}
      <div className="prose prose-sm max-w-none">
        <pre className="whitespace-pre-wrap text-sm text-gray-800">{content}</pre>
      </div>
    </div>
  )
}
