/**
 * Frontend Performance Monitoring Utility
 * Track and report performance metrics
 */

class PerformanceMonitor {
  constructor() {
    this.metrics = {
      api_calls: [],
      page_loads: [],
      renders: {},
      errors: []
    };
    
    this.thresholds = {
      api_slow: 1000, // ms
      render_slow: 100, // ms
      page_load_slow: 3000 // ms
    };
  }

  /**
   * Track API call performance
   */
  trackAPICall(endpoint, duration, status) {
    const metric = {
      endpoint,
      duration,
      status,
      timestamp: Date.now(),
      slow: duration > this.thresholds.api_slow
    };
    
    this.metrics.api_calls.push(metric);
    
    // Keep only last 100 API calls
    if (this.metrics.api_calls.length > 100) {
      this.metrics.api_calls.shift();
    }
    
    if (metric.slow) {
      console.warn(`⚠️ Slow API call: ${endpoint} (${duration}ms)`);
    }
    
    return metric;
  }

  /**
   * Track page load performance
   */
  trackPageLoad(page, duration) {
    const metric = {
      page,
      duration,
      timestamp: Date.now(),
      slow: duration > this.thresholds.page_load_slow
    };
    
    this.metrics.page_loads.push(metric);
    
    if (metric.slow) {
      console.warn(`⚠️ Slow page load: ${page} (${duration}ms)`);
    }
    
    return metric;
  }

  /**
   * Track component render performance
   */
  trackRender(componentName, duration) {
    if (!this.metrics.renders[componentName]) {
      this.metrics.renders[componentName] = {
        count: 0,
        total_time: 0,
        avg_time: 0,
        slow_renders: 0
      };
    }
    
    const render = this.metrics.renders[componentName];
    render.count++;
    render.total_time += duration;
    render.avg_time = render.total_time / render.count;
    
    if (duration > this.thresholds.render_slow) {
      render.slow_renders++;
      console.warn(`⚠️ Slow render: ${componentName} (${duration}ms)`);
    }
    
    return render;
  }

  /**
   * Track errors
   */
  trackError(error, context = {}) {
    const errorMetric = {
      message: error.message || String(error),
      stack: error.stack,
      context,
      timestamp: Date.now()
    };
    
    this.metrics.errors.push(errorMetric);
    
    // Keep only last 50 errors
    if (this.metrics.errors.length > 50) {
      this.metrics.errors.shift();
    }
    
    console.error('❌ Error tracked:', errorMetric);
    
    return errorMetric;
  }

  /**
   * Get performance summary
   */
  getSummary() {
    const apiCalls = this.metrics.api_calls;
    const pageLoads = this.metrics.page_loads;
    
    return {
      api_calls: {
        total: apiCalls.length,
        slow: apiCalls.filter(c => c.slow).length,
        avg_duration: apiCalls.length > 0 
          ? Math.round(apiCalls.reduce((sum, c) => sum + c.duration, 0) / apiCalls.length)
          : 0,
        fastest: apiCalls.length > 0 
          ? Math.min(...apiCalls.map(c => c.duration))
          : 0,
        slowest: apiCalls.length > 0 
          ? Math.max(...apiCalls.map(c => c.duration))
          : 0
      },
      page_loads: {
        total: pageLoads.length,
        slow: pageLoads.filter(p => p.slow).length,
        avg_duration: pageLoads.length > 0
          ? Math.round(pageLoads.reduce((sum, p) => sum + p.duration, 0) / pageLoads.length)
          : 0
      },
      renders: this.metrics.renders,
      errors: {
        total: this.metrics.errors.length,
        recent: this.metrics.errors.slice(-5)
      }
    };
  }

  /**
   * Get slow operations
   */
  getSlowOperations() {
    return {
      api_calls: this.metrics.api_calls
        .filter(c => c.slow)
        .sort((a, b) => b.duration - a.duration)
        .slice(0, 10),
      page_loads: this.metrics.page_loads
        .filter(p => p.slow)
        .sort((a, b) => b.duration - a.duration)
        .slice(0, 10),
      renders: Object.entries(this.metrics.renders)
        .filter(([_, r]) => r.slow_renders > 0)
        .sort((a, b) => b[1].slow_renders - a[1].slow_renders)
        .slice(0, 10)
        .map(([name, stats]) => ({ component: name, ...stats }))
    };
  }

  /**
   * Clear all metrics
   */
  clear() {
    this.metrics = {
      api_calls: [],
      page_loads: [],
      renders: {},
      errors: []
    };
  }

  /**
   * Export metrics to JSON
   */
  export() {
    return {
      metrics: this.metrics,
      summary: this.getSummary(),
      slow_operations: this.getSlowOperations(),
      timestamp: Date.now()
    };
  }

  /**
   * Print performance report to console
   */
  printReport() {
    const summary = this.getSummary();
    
    console.log('📊 Performance Report');
    console.log('═══════════════════════════════════════');
    
    console.log('\n📡 API Calls:');
    console.log(`  Total: ${summary.api_calls.total}`);
    console.log(`  Slow (>${this.thresholds.api_slow}ms): ${summary.api_calls.slow}`);
    console.log(`  Avg Duration: ${summary.api_calls.avg_duration}ms`);
    console.log(`  Range: ${summary.api_calls.fastest}ms - ${summary.api_calls.slowest}ms`);
    
    console.log('\n📄 Page Loads:');
    console.log(`  Total: ${summary.page_loads.total}`);
    console.log(`  Slow (>${this.thresholds.page_load_slow}ms): ${summary.page_loads.slow}`);
    console.log(`  Avg Duration: ${summary.page_loads.avg_duration}ms`);
    
    console.log('\n🎨 Component Renders:');
    const topRenders = Object.entries(summary.renders)
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 5);
    
    topRenders.forEach(([name, stats]) => {
      console.log(`  ${name}:`);
      console.log(`    Renders: ${stats.count}`);
      console.log(`    Avg: ${Math.round(stats.avg_time)}ms`);
      console.log(`    Slow: ${stats.slow_renders}`);
    });
    
    console.log('\n❌ Errors:');
    console.log(`  Total: ${summary.errors.total}`);
    
    if (summary.errors.recent.length > 0) {
      console.log('  Recent:');
      summary.errors.recent.forEach(err => {
        console.log(`    - ${err.message}`);
      });
    }
    
    console.log('\n═══════════════════════════════════════');
  }
}

// Create singleton instance
const performanceMonitor = new PerformanceMonitor();

// Auto-print report every 5 minutes in development
if (process.env.NODE_ENV === 'development') {
  setInterval(() => {
    performanceMonitor.printReport();
  }, 5 * 60 * 1000);
}

export default performanceMonitor;

// HOC for tracking component renders
export const withPerformanceTracking = (WrappedComponent) => {
  const componentName = WrappedComponent.displayName || WrappedComponent.name || 'Component';
  
  return (props) => {
    const startTime = performance.now();
    
    React.useEffect(() => {
      const duration = performance.now() - startTime;
      performanceMonitor.trackRender(componentName, duration);
    });
    
    return <WrappedComponent {...props} />;
  };
};
