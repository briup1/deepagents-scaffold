interface NewChatButtonProps {
  onClick: () => void
}

function PlusIcon() {
  return (
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
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

export function NewChatButton({ onClick }: NewChatButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-center gap-2 rounded-xl border border-cream-300 bg-white px-4 py-2.5 text-sm font-semibold text-ink shadow-soft transition hover:bg-cream-50 hover:shadow-input focus:outline-none focus:ring-2 focus:ring-blue-500/20 active:scale-[0.98]"
    >
      <PlusIcon />
      新建会话
    </button>
  )
}
