export interface GenerativeUIMetadata {
  type: 'markdown_card' | 'data_table'
  title?: string
}

export interface MarkdownCardMetadata extends GenerativeUIMetadata {
  type: 'markdown_card'
  content: string
}

export interface DataTableMetadata extends GenerativeUIMetadata {
  type: 'data_table'
  columns: Array<{ key: string; label: string }>
  rows: Array<Record<string, string | number | boolean>>
}

export function isMarkdownCard(
  metadata: GenerativeUIMetadata,
): metadata is MarkdownCardMetadata {
  return metadata.type === 'markdown_card'
}

export function isDataTable(
  metadata: GenerativeUIMetadata,
): metadata is DataTableMetadata {
  return metadata.type === 'data_table'
}
