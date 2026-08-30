import { apiFetch } from "./auth"
export interface UploadedFile {
  artifact_id: string
  thread_id: string
  artifact_type: string
  original_name: string
  stored_path: string
  mime_type: string | null
  size_bytes: number
  created_at: string
}

export async function uploadFile(threadId: string, file: File): Promise<UploadedFile> {
  const formData = new FormData()
  formData.append('thread_id', threadId)
  formData.append('file', file)

  const res = await apiFetch('/api/files/upload', {
    method: 'POST',
    body: formData,
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`上传失败 (${res.status}): ${text}`)
  }

  return res.json()
}

export async function listFiles(
  threadId: string,
  artifactType?: string,
): Promise<{ artifacts: UploadedFile[]; total: number }> {
  const params = new URLSearchParams()
  params.set('thread_id', threadId)
  if (artifactType) params.set('artifact_type', artifactType)

  const res = await apiFetch(`/api/files/?${params.toString()}`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`获取文件列表失败 (${res.status}): ${text}`)
  }

  return res.json()
}
