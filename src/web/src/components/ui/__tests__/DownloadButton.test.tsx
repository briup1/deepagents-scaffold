import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, expect } from 'vitest'
import { DownloadButton } from '../DownloadButton'

describe('DownloadButton', () => {
  it('renders description and button', () => {
    render(<DownloadButton artifact_id="art-123" file_name="data.csv" description="点击下载" />)
    expect(screen.getByText('点击下载')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /下载 data.csv/ })).toBeInTheDocument()
  })

  it('triggers download on click', async () => {
    const blob = new Blob(['a,b\n1,2'], { type: 'text/csv' })
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      blob: () => Promise.resolve(blob),
    } as unknown as Response)
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:mock-url'),
      revokeObjectURL: vi.fn(),
    })

    const createElementSpy = vi.spyOn(document, 'createElement')
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click')

    render(<DownloadButton artifact_id="art-123" file_name="data.csv" />)
    await userEvent.click(screen.getByRole('button'))

    expect(fetchMock).toHaveBeenCalledWith('/api/files/art-123/download')
    expect(createElementSpy).toHaveBeenCalledWith('a')
    expect(clickSpy).toHaveBeenCalled()

    vi.unstubAllGlobals()
  })
})
