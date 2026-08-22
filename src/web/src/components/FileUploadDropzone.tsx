import { useCallback, useState, type DragEvent, type ReactNode } from 'react'
import type { UploadedFile } from '../api/files'

interface FileUploadDropzoneProps {
  threadId: string
  onFileUploaded: (file: UploadedFile) => void
  children: ReactNode
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function FileUploadDropzone({
  threadId,
  onFileUploaded,
  children,
}: FileUploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(
    async (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)
      setError(null)

      const files = Array.from(e.dataTransfer.files)
      if (files.length === 0) return

      const file = files[0]
      const validExts = ['.xlsx', '.xls']
      const validMimes = [
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
      ]
      const extValid = validExts.some((ext) => file.name.toLowerCase().endsWith(ext))
      const mimeValid = validMimes.includes(file.type)

      if (!extValid && !mimeValid) {
        setError('仅支持 Excel 文件（.xlsx 或 .xls）')
        return
      }

      if (file.size > 20 * 1024 * 1024) {
        setError('文件大小超过 20MB 限制')
        return
      }

      try {
        const { uploadFile } = await import('../api/files')
        const uploaded = await uploadFile(threadId, file)
        onFileUploaded(uploaded)
      } catch (err) {
        setError(err instanceof Error ? err.message : '上传失败')
      }
    },
    [threadId, onFileUploaded],
  )

  return (
    <div
      className="relative flex h-full w-full flex-col"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center rounded-2xl border-2 border-dashed border-blue-500 bg-blue-50/80">
          <p className="text-lg font-medium text-blue-600">释放以上传 Excel 文件</p>
        </div>
      )}
      {error && (
        <div className="absolute right-4 top-4 z-50 rounded-lg bg-red-100 px-4 py-2 text-sm text-red-700 shadow">
          {error}
        </div>
      )}
      {children}
    </div>
  )
}

export function FileAttachmentChip({
  file,
  onRemove,
}: {
  file: UploadedFile
  onRemove?: () => void
}) {
  return (
    <div className="flex items-center gap-2 rounded-full bg-blue-50 px-3 py-1 text-sm text-blue-700">
      <span className="truncate max-w-[160px]">{file.original_name}</span>
      <span className="text-xs text-blue-400">{formatBytes(file.size_bytes)}</span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="ml-1 rounded-full p-0.5 hover:bg-blue-100"
          aria-label="移除文件"
        >
          ×
        </button>
      )}
    </div>
  )
}
