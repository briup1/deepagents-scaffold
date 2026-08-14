interface Button {
  id: string
  label: string
}

interface ButtonGroupProps {
  title?: string
  buttons: Button[]
  surfaceId?: string
  dispatch: (action: unknown) => void
}

export function ButtonGroup({ title, buttons, surfaceId, dispatch }: ButtonGroupProps) {
  return (
    <div className="my-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      {title && <h3 className="mb-3 text-sm font-semibold text-gray-700">{title}</h3>}
      <div className="flex flex-wrap gap-2">
        {buttons.map((button) => (
          <button
            key={button.id}
            type="button"
            onClick={() =>
              dispatch({
                type: 'button_click',
                surfaceId,
                id: button.id,
              })
            }
            className="rounded border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            {button.label}
          </button>
        ))}
      </div>
    </div>
  )
}
