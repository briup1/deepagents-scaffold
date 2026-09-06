import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { uploadFile, type UploadedFile } from '../../api/files'
import { FileUploadDropzone } from '../FileUploadDropzone'

vi.mock('../../api/files', () => ({
  uploadFile: vi.fn(),
}))

const mockUploadFile = vi.mocked(uploadFile)

const UPLOADED: UploadedFile = {
  artifact_id: 'art-1',
  original_name: 'data.xlsx',
  size_bytes: 10,
}

function makeExcelFile(name = 'data.xlsx'): File {
  return new File(['x'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
}

function renderDropzone(onFileUploaded = vi.fn()) {
  return render(
    <FileUploadDropzone threadId="t-1" onFileUploaded={onFileUploaded}>
      <div>chat-content</div>
    </FileUploadDropzone>,
  )
}

function pickFile(container: HTMLElement, files: File[]) {
  const input = container.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) throw new Error('file input not found')
  fireEvent.change(input, { target: { files } })
}

describe('FileUploadDropzone', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('上传成功路径不输出 console.log 调试日志', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    mockUploadFile.mockResolvedValue(UPLOADED)
    const onFileUploaded = vi.fn()

    const { container } = renderDropzone(onFileUploaded)
    pickFile(container, [makeExcelFile()])

    await waitFor(() => expect(onFileUploaded).toHaveBeenCalledWith(UPLOADED))
    expect(logSpy).not.toHaveBeenCalled()
    logSpy.mockRestore()
  })

  it('上传失败路径不输出 console.log，且向用户暴露错误提示', async () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {})
    mockUploadFile.mockRejectedValue(new Error('网络错误'))

    const { container } = renderDropzone()
    pickFile(container, [makeExcelFile()])

    await waitFor(() => expect(screen.getByText('data.xlsx: 网络错误')).toBeInTheDocument())
    expect(logSpy).not.toHaveBeenCalled()
    logSpy.mockRestore()
  })
})
