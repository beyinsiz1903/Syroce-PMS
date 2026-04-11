import { useState, useEffect, useRef } from 'react';

/**
 * Custom hook for real-time data updates
 * @param {Function} fetchFunction - Function to fetch data
 * @param {number} interval - Update interval in milliseconds (default: 30000 = 30 seconds)
 * @param {boolean} enabled - Enable/disable auto-refresh
 */
const useRealTimeData = (fetchFunction, interval = 30000, enabled = true) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const intervalRef = useRef(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const result = await fetchFunction();
      setData(result);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      console.error('Error fetching real-time data:', err);
      setError(err.message || 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  const refresh = () => {
    fetchData();
  };

  useEffect(() => {
    // Initial fetch
    fetchData();

    // Set up interval for auto-refresh
    if (enabled && interval > 0) {
      intervalRef.current = setInterval(() => {
        fetchData();
      }, interval);
    }

    // Cleanup
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [enabled, interval]);

  return {
    data,
    loading,
    error,
    lastUpdate,
    refresh
  };
};

export default useRealTimeData;
