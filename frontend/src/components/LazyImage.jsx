/**
 * Lazy Loading Image Component
 * Optimized image loading with placeholder and caching
 */
import { useState, useEffect, useRef } from 'react';
import { useIsMobile } from '@/hooks/useMobileOptimization';

const LazyImage = ({
  src,
  alt,
  className = '',
  placeholder = '/placeholder.svg',
  lowQualitySrc = null,
  width,
  height,
  onLoad,
  onError,
  threshold = 0.1,
  rootMargin = '50px',
}) => {
  const [imageSrc, setImageSrc] = useState(placeholder);
  const [imageRef, setImageRef] = useState();
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const isMobile = useIsMobile();
  
  const imgRef = useRef();

  useEffect(() => {
    let observer;
    let didCancel = false;

    if (imgRef.current && imageSrc === placeholder) {
      if (IntersectionObserver) {
        observer = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (
                !didCancel &&
                (entry.intersectionRatio > 0 || entry.isIntersecting)
              ) {
                setImageRef(imgRef.current);
                observer.unobserve(imgRef.current);
              }
            });
          },
          {
            threshold,
            rootMargin,
          }
        );
        observer.observe(imgRef.current);
      } else {
        // Fallback if IntersectionObserver not supported
        setImageRef(imgRef.current);
      }
    }

    return () => {
      didCancel = true;
      if (observer && observer.unobserve) {
        observer.unobserve(imgRef.current);
      }
    };
  }, [imageSrc, placeholder, threshold, rootMargin]);

  useEffect(() => {
    if (imageRef && imageSrc === placeholder) {
      // Load low quality image first if available
      if (lowQualitySrc) {
        const lowQualityImg = new Image();
        lowQualityImg.src = lowQualitySrc;
        lowQualityImg.onload = () => {
          setImageSrc(lowQualitySrc);
        };
      }

      // Load high quality image
      const highQualityImg = new Image();
      highQualityImg.src = src;
      
      highQualityImg.onload = () => {
        setImageSrc(src);
        setIsLoading(false);
        if (onLoad) onLoad();
      };
      
      highQualityImg.onerror = () => {
        setHasError(true);
        setIsLoading(false);
        if (onError) onError();
      };
    }
  }, [imageRef, imageSrc, placeholder, src, lowQualitySrc, onLoad, onError]);

  return (
    <div className={`lazy-image-container ${className}`} style={{ position: 'relative' }}>
      <img
        ref={imgRef}
        src={imageSrc}
        alt={alt}
        width={width}
        height={height}
        className={`
          lazy-image
          ${isLoading ? 'loading' : 'loaded'}
          ${hasError ? 'error' : ''}
        `}
        style={{
          opacity: isLoading ? 0.5 : 1,
          filter: isLoading ? 'blur(5px)' : 'none',
          transition: 'opacity 0.3s ease-in-out, filter 0.3s ease-in-out',
        }}
      />
      
      {isLoading && (
        <div
          className="lazy-image-loader"
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
          }}
        >
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      )}
      
      {hasError && (
        <div
          className="lazy-image-error"
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            textAlign: 'center',
            color: '#ef4444',
          }}
        >
          <svg
            className="w-12 h-12 mx-auto"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <p className="text-sm mt-2">Failed to load image</p>
        </div>
      )}
    </div>
  );
};

export default LazyImage;

/**
 * Lazy Background Image Hook
 * For div backgrounds
 */
export const useLazyBackgroundImage = (src, placeholder = '') => {
  const [backgroundImage, setBackgroundImage] = useState(placeholder);
  const [isLoaded, setIsLoaded] = useState(false);
  const elementRef = useRef();

  useEffect(() => {
    let observer;
    let didCancel = false;

    if (elementRef.current) {
      if (IntersectionObserver) {
        observer = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (
                !didCancel &&
                (entry.intersectionRatio > 0 || entry.isIntersecting)
              ) {
                const img = new Image();
                img.src = src;
                
                img.onload = () => {
                  setBackgroundImage(src);
                  setIsLoaded(true);
                };
                
                observer.unobserve(elementRef.current);
              }
            });
          },
          {
            threshold: 0.01,
            rootMargin: '50px',
          }
        );
        observer.observe(elementRef.current);
      } else {
        const img = new Image();
        img.src = src;
        img.onload = () => {
          setBackgroundImage(src);
          setIsLoaded(true);
        };
      }
    }

    return () => {
      didCancel = true;
      if (observer && observer.unobserve && elementRef.current) {
        observer.unobserve(elementRef.current);
      }
    };
  }, [src, placeholder]);

  return { backgroundImage, isLoaded, elementRef };
};
