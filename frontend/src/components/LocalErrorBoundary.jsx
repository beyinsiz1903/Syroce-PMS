import React from 'react';
import ProductState from '@/components/shared/ProductState';
class LocalErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error("LocalErrorBoundary caught an error:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <ProductState
          state="error"
          compact
          onRetry={() => this.setState({ hasError: false, error: null })}
          showDashboardLink={false}
        />
      );
    }
    return this.props.children;
  }
}
export default LocalErrorBoundary;
