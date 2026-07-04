import React from 'react';
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
        <div className="p-8 m-4 bg-red-50 border border-red-200 rounded text-red-800">
          <h2 className="text-lg font-bold mb-2">Bileşen Yüklenirken Hata Oluştu</h2>
          <pre className="text-sm overflow-auto">{this.state.error && this.state.error.toString()}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}
export default LocalErrorBoundary;
