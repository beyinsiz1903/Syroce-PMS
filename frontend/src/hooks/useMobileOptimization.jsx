/**
 * Mobile Optimization Hook
 * Optimizes data fetching for mobile devices
 */
import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

/**
 * Detect if device is mobile
 */
export const useIsMobile = () => {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  return isMobile;
};

/**
 * Detect network speed
 */
export const useNetworkSpeed = () => {
  const [networkSpeed, setNetworkSpeed] = useState('4g');

  useEffect(() => {
    if ('connection' in navigator) {
      const connection = navigator.connection;
      setNetworkSpeed(connection.effectiveType || '4g');

      const handleChange = () => {
        setNetworkSpeed(connection.effectiveType || '4g');
      };

      connection.addEventListener('change', handleChange);
      return () => connection.removeEventListener('change', handleChange);
    }
  }, []);

  return networkSpeed;
};

/**
 * Optimize query settings based on device and network
 */
export const useMobileQueryConfig = () => {
  const isMobile = useIsMobile();
  const networkSpeed = useNetworkSpeed();
  const queryClient = useQueryClient();

  const isSlowConnection = ['slow-2g', '2g', '3g'].includes(networkSpeed);

  // Adjust cache times based on network speed
  const config = {
    staleTime: isSlowConnection ? 10 * 60 * 1000 : 5 * 60 * 1000, // 10 min vs 5 min
    cacheTime: isSlowConnection ? 30 * 60 * 1000 : 15 * 60 * 1000, // 30 min vs 15 min
    refetchOnWindowFocus: !isSlowConnection, // Don't refetch on slow connections
    refetchOnMount: isSlowConnection ? false : 'stale', // Only refetch if stale
    retry: isSlowConnection ? 1 : 2, // Fewer retries on slow connections
  };

  // Reduce concurrent requests on mobile
  useEffect(() => {
    if (isMobile) {
      // Limit concurrent queries
      queryClient.setDefaultOptions({
        queries: {
          ...config,
          networkMode: isSlowConnection ? 'offlineFirst' : 'online',
        },
      });
    }
  }, [isMobile, isSlowConnection, queryClient]);

  return {
    isMobile,
    networkSpeed,
    isSlowConnection,
    queryConfig: config,
  };
};

/**
 * Adaptive image loading
 */
export const useAdaptiveImages = () => {
  const isMobile = useIsMobile();
  const networkSpeed = useNetworkSpeed();

  const getImageQuality = () => {
    if (['slow-2g', '2g'].includes(networkSpeed)) return 'low';
    if (networkSpeed === '3g') return 'medium';
    return 'high';
  };

  const getImageSize = (baseSize) => {
    const quality = getImageQuality();
    if (quality === 'low') return Math.floor(baseSize * 0.5);
    if (quality === 'medium') return Math.floor(baseSize * 0.75);
    return baseSize;
  };

  return {
    imageQuality: getImageQuality(),
    getImageSize,
    shouldLoadImages: networkSpeed !== 'slow-2g',
  };
};

/**
 * Battery-aware optimization
 */
export const useBatteryOptimization = () => {
  const [batteryLevel, setBatteryLevel] = useState(1);
  const [isCharging, setIsCharging] = useState(true);

  useEffect(() => {
    if ('getBattery' in navigator) {
      navigator.getBattery().then((battery) => {
        setBatteryLevel(battery.level);
        setIsCharging(battery.charging);

        battery.addEventListener('levelchange', () => {
          setBatteryLevel(battery.level);
        });

        battery.addEventListener('chargingchange', () => {
          setIsCharging(battery.charging);
        });
      });
    }
  }, []);

  const shouldOptimize = !isCharging && batteryLevel < 0.2; // Optimize if battery < 20% and not charging

  return {
    batteryLevel,
    isCharging,
    shouldOptimize,
    batteryPercentage: Math.round(batteryLevel * 100),
  };
};

/**
 * Visibility-based data fetching
 * Only fetch data when page is visible
 */
export const useVisibilityOptimization = () => {
  const [isVisible, setIsVisible] = useState(!document.hidden);

  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsVisible(!document.hidden);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  return { isVisible };
};

/**
 * Combined mobile optimization hook
 */
export const useMobileOptimizations = () => {
  const { isMobile, isSlowConnection, queryConfig } = useMobileQueryConfig();
  const { imageQuality, shouldLoadImages } = useAdaptiveImages();
  const { shouldOptimize: shouldOptimizeBattery, batteryPercentage } = useBatteryOptimization();
  const { isVisible } = useVisibilityOptimization();

  // Determine if we should be in "lite mode"
  const liteMode = isSlowConnection || shouldOptimizeBattery || !shouldLoadImages;

  return {
    isMobile,
    isSlowConnection,
    liteMode,
    imageQuality,
    shouldLoadImages,
    batteryPercentage,
    isVisible,
    queryConfig,
    
    // Recommendations
    recommendations: {
      reduceAnimations: liteMode,
      reducePolling: liteMode,
      prefetchData: !liteMode && isVisible,
      loadHighResImages: !liteMode && !isMobile,
    },
  };
};
