import React from 'react';

/**
 * SkeletonRow — Animated loading placeholder for table/list tabs.
 *
 * Props:
 *   cols  {number} Number of columns per row (default 3)
 *   rows  {number} Number of skeleton rows to render (default 5)
 */
export default function SkeletonRow({ cols = 3, rows = 5 }) {
  return (
    <div style={styles.wrapper} aria-busy="true" aria-label="Yükleniyor">
      {Array.from({ length: rows }).map((_, ri) => (
        <div key={ri} style={styles.row}>
          {Array.from({ length: cols }).map((_, ci) => (
            <div
              key={ci}
              style={{
                ...styles.cell,
                width: ci === 0 ? '35%' : ci === 1 ? '30%' : '25%',
              }}
            />
          ))}
        </div>
      ))}
      <style>{`
        @keyframes hr-skeleton-pulse {
          0% { opacity: 1; }
          50% { opacity: 0.4; }
          100% { opacity: 1; }
        }
        .hr-skeleton-cell {
          animation: hr-skeleton-pulse 1.4s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}

const styles = {
  wrapper: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    padding: '8px 0',
  },
  row: {
    display: 'flex',
    gap: '12px',
    alignItems: 'center',
  },
  cell: {
    height: '18px',
    borderRadius: '6px',
    background: 'var(--skeleton-bg, #e5e7eb)',
    animation: 'hr-skeleton-pulse 1.4s ease-in-out infinite',
    flex: '0 0 auto',
  },
};
