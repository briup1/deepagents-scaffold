import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Form } from '../Form'

describe('Form', () => {
  it('renders fields and submits dispatch', async () => {
    const dispatch = vi.fn()
    render(
      <Form
        title="Survey"
        fields={[
          { name: 'name', label: 'Name' },
          { name: 'age', label: 'Age', type: 'number' },
        ]}
        dispatch={dispatch}
        surfaceId="s1"
      />,
    )

    expect(screen.getByText('Survey')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Name'), 'Alice')
    await user.type(screen.getByLabelText('Age'), '30')
    await user.click(screen.getByRole('button', { name: '提交' }))

    expect(dispatch).toHaveBeenCalledWith({
      type: 'form_submit',
      surfaceId: 's1',
      values: { name: 'Alice', age: '30' },
    })
  })
})
