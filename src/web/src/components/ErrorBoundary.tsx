import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen flex-col items-center justify-center p-4 text-center">
          <h1 className="text-xl font-semibold text-red-600">出错了</h1>
          <p className="mt-2 text-sm text-gray-600">
            {this.state.error?.message || '未知错误'}
          </p>
          <button
            className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm text-white"
            onClick={() => window.location.reload()}
          >
            刷新页面
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
