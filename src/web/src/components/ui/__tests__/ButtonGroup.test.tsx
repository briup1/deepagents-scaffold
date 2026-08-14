import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ButtonGroup } from '../ButtonGroup'

describe('ButtonGroup', () => {
  it('renders buttons and dispatches click', async () => {
    const dispatch = vi.fn()
    render(
      <ButtonGroup
        title="Actions"
        buttons={[
          { id: 'ok', label: 'OK' },
          { id: 'cancel', label: 'Cancel' },
        ]}
        dispatch={dispatch}
        surfaceId="s2"
      />,
    )

    expect(screen.getByText('Actions')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'OK' }))

    expect(dispatch).toHaveBeenCalledWith({
      type: 'button_click',
      surfaceId: 's2',
      id: 'ok',
    })
  })
})
