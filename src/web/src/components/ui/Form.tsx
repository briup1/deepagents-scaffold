import { useState } from 'react'

export interface FormField {
  name: string
  label: string
  type?: 'text' | 'number'
}

interface FormProps {
  title?: string
  fields: FormField[]
  submitLabel?: string
  surfaceId?: string
  dispatch: (action: unknown) => void
}

export function Form({ title, fields, submitLabel = '提交', surfaceId, dispatch }: FormProps) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {}
    for (const field of fields) {
      initial[field.name] = ''
    }
    return initial
  })

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    dispatch({
      type: 'form_submit',
      surfaceId,
      values,
    })
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="my-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
    >
      {title && <h3 className="mb-3 text-sm font-semibold text-gray-700">{title}</h3>}
      <div className="space-y-3">
        {fields.map((field) => (
          <div key={field.name}>
            <label htmlFor={`field-${field.name}`} className="block text-xs font-medium text-gray-600">
              {field.label}
            </label>
            <input
              id={`field-${field.name}`}
              type={field.type === 'number' ? 'number' : 'text'}
              value={values[field.name] ?? ''}
              onChange={(e) =>
                setValues((prev) => ({ ...prev, [field.name]: e.target.value }))
              }
              className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
            />
          </div>
        ))}
      </div>
      <button
        type="submit"
        className="mt-4 rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
      >
        {submitLabel}
      </button>
    </form>
  )
}
