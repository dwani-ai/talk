import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error) {
    // eslint-disable-next-line no-console
    console.error('Unhandled UI error:', error)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div role="alert" style={{ padding: '1rem' }}>
          Something went wrong. Please refresh the page.
        </div>
      )
    }
    return this.props.children
  }
}
