import type { ReactNode } from 'react'

export interface DownloadButtonProps {
  artifact_id: string
  file_name: string
  description?: string
}

export function DownloadButton({ artifact_id, file_name, description }: DownloadButtonProps): ReactNode {
  const handleClick = async () => {
    try {
      const response = await fetch(`/api/files/${artifact_id}/download`)
      if (!response.ok) {
        throw new Error(`下载失败 (${response.status}): ${await response.text()}`)
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = file_name
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('[DownloadButton] 下载失败:', err)
      alert(err instanceof Error ? err.message : '下载失败')
    }
  }

  return (
    <div className="my-2 rounded-lg border border-blue-200 bg-blue-50 p-4">
      {description && <p className="mb-2 text-sm text-blue-800">{description}</p>}
      <button
        type="button"
        onClick={handleClick}
        className="inline-flex items-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
      >
        下载 {file_name}
      </button>
    </div>
  )
}
