import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
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
  children,
}: FileUploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const processFile = useCallback(
    async (file: File) => {
      setError(null)
      console.log('[FileUpload] processing file:', file.name, file.type, file.size)

      if (!isExcelFile(file)) {
        const msg = '仅支持 Excel 文件（.xlsx 或 .xls）'
        console.warn('[FileUpload] rejected:', msg)
        setError(msg)
        return
      }

      if (file.size > MAX_FILE_SIZE) {
        const msg = '文件大小超过 20MB 限制'
        console.warn('[FileUpload] rejected:', msg)
        setError(msg)
        return
      }

      try {
        console.log('[FileUpload] uploading to /api/files/upload, threadId:', threadId)
        const uploaded = await uploadFile(threadId, file)
        console.log('[FileUpload] upload success:', uploaded)
        onFileUploaded(uploaded)
      } catch (err) {
        const msg = err instanceof Error ? err.message : '上传失败'
        console.error('[FileUpload] upload error:', err)
        setError(msg)
      }
    },
    [threadId, onFileUploaded],
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

      await processFile(files[0])
    }

    document.addEventListener('dragenter', handleDragEnter)
    document.addEventListener('dragover', handleDragOver)
    document.addEventListener('dragleave', handleDragLeave)
    document.addEventListener('drop', handleDrop)

    return () => {
      document.removeEventListener('dragenter', handleDragEnter)
      document.removeEventListener('dragover', handleDragOver)
      document.removeEventListener('dragleave', handleDragLeave)
      document.removeEventListener('drop', handleDrop)
    }
  }, [processFile])

  const handleFileInputChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files
      if (!files || files.length === 0) return
      await processFile(files[0])
      e.target.value = ''
    },
    [processFile],
  )

  const handleClickUpload = useCallback(() => {
    inputRef.current?.click()
  }, [])

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
      <button
        type="button"
        onClick={handleClickUpload}
        className="absolute right-4 top-4 z-40 rounded-full bg-blue-600 p-2.5 text-white shadow-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
        title="上传 Excel 文件"
        aria-label="上传 Excel 文件"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
        onChange={handleFileInputChange}
        className="hidden"
      />
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
