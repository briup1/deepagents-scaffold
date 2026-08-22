import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { uploadFile, type UploadedFile } from '../api/files'

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

const VALID_EXTS = ['.xlsx', '.xls']
const VALID_MIMES = [
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
]
const MAX_FILE_SIZE = 20 * 1024 * 1024

function isExcelFile(file: File): boolean {
  const extValid = VALID_EXTS.some((ext) => file.name.toLowerCase().endsWith(ext))
  const mimeValid = VALID_MIMES.includes(file.type)
  return extValid || mimeValid
}

export function FileUploadDropzone({
  threadId,
  onFileUploaded,
  onError,
  children,
}: FileUploadDropzoneProps & { onError?: (message: string) => void }) {
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reportError = useCallback(
    (message: string) => {
      setError(message)
      onError?.(message)
    },
    [onError],
  )

  const processFiles = useCallback(
    async (files: File[]) => {
      setError(null)
      const excelFiles = files.filter((file) => {
        const ok = isExcelFile(file)
        if (!ok) {
          console.warn('[FileUpload] rejected non-excel:', file.name)
        }
        return ok
      })

      if (excelFiles.length === 0) {
        reportError('未检测到 Excel 文件（.xlsx 或 .xls）')
        return
      }

      const oversized = excelFiles.filter((file) => file.size > MAX_FILE_SIZE)
      if (oversized.length > 0) {
        reportError(`以下文件超过 20MB：${oversized.map((f) => f.name).join(', ')}`)
        return
      }

      for (const file of excelFiles) {
        try {
          console.log('[FileUpload] uploading:', file.name)
          const uploaded = await uploadFile(threadId, file)
          console.log('[FileUpload] upload success:', uploaded)
          onFileUploaded(uploaded)
        } catch (err) {
          const msg = err instanceof Error ? err.message : '上传失败'
          console.error('[FileUpload] upload error:', file.name, err)
          reportError(`${file.name}: ${msg}`)
        }
      }
    },
    [threadId, onFileUploaded, reportError],
  )

  // 在 document 级别监听拖拽，避免 CopilotChat 内部元素阻止事件冒泡
  useEffect(() => {
    const handleDragEnter = (e: globalThis.DragEvent) => {
      e.preventDefault()
      setIsDragging(true)
    }

    const handleDragOver = (e: globalThis.DragEvent) => {
      e.preventDefault()
      setIsDragging(true)
    }

    const handleDragLeave = (e: globalThis.DragEvent) => {
      e.preventDefault()
      const related = e.relatedTarget as Node | null
      if (!related || related === document.body || related === document.documentElement) {
        setIsDragging(false)
      }
    }

    const handleDrop = async (e: globalThis.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setIsDragging(false)

      const files = Array.from(e.dataTransfer?.files ?? [])
      console.log('[FileUpload] dropped files:', files.length)
      if (files.length === 0) {
        setError('未检测到文件，请重新拖拽')
        return
      }

      await processFiles(files)
    }

    document.addEventListener('dragenter', handleDragEnter, true)
    document.addEventListener('dragover', handleDragOver, true)
    document.addEventListener('dragleave', handleDragLeave, true)
    document.addEventListener('drop', handleDrop, true)

    return () => {
      document.removeEventListener('dragenter', handleDragEnter, true)
      document.removeEventListener('dragover', handleDragOver, true)
      document.removeEventListener('dragleave', handleDragLeave, true)
      document.removeEventListener('drop', handleDrop, true)
    }
  }, [processFiles])

  return (
    <div className="relative flex h-full w-full flex-col">
      {isDragging && (
        <div className="pointer-events-none fixed inset-0 z-[100] flex items-center justify-center border-4 border-dashed border-blue-500 bg-blue-50/90">
          <p className="text-2xl font-semibold text-blue-600">释放以上传 Excel 文件</p>
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

export function FileAttachmentList({
  files,
  onRemove,
}: {
  files: UploadedFile[]
  onRemove?: (artifactId: string) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-blue-100 bg-blue-50/70 p-3 shadow-sm">
      <div className="flex shrink-0 items-center gap-2 text-sm font-medium text-blue-800">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
        已上传文件（{files.length}）
      </div>
      {files.map((file) => (
        <div
          key={file.artifact_id}
          className="flex min-w-0 max-w-[260px] items-center gap-2 rounded-lg bg-white px-2.5 py-1.5 text-sm shadow-sm"
          title={`${file.original_name}（${file.artifact_id}）`}
        >
          <span className="truncate text-blue-700">{file.original_name}</span>
          <span className="shrink-0 text-xs text-slate-400">{formatBytes(file.size_bytes)}</span>
          {onRemove && (
            <button
              type="button"
              onClick={() => onRemove(file.artifact_id)}
              className="rounded-full p-0.5 text-slate-400 hover:bg-blue-50 hover:text-red-500"
              aria-label="移除文件"
            >
              ×
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
