import React from 'react';

/**
 * PaginationBar — Shared pagination control component.
 *
 * Props:
 *   page         {number}   Current page (1-indexed)
 *   totalPages   {number}   Total number of pages
 *   total        {number}   Total record count (for display)
 *   limit        {number}   Current page size
 *   onPageChange {function} Called with new page number
 *   onLimitChange{function} Called with new limit value (optional)
 *   pageSizes    {number[]} Available page size options (default [10,25,50,100])
 */
export default function PaginationBar({
  page = 1,
  totalPages = 1,
  total = 0,
  limit = 25,
  onPageChange,
  onLimitChange,
  pageSizes = [10, 25, 50, 100],
}) {
  const from = total === 0 ? 0 : (page - 1) * limit + 1;
  const to = Math.min(page * limit, total);

  return (
    <div style={styles.container}>
      {/* Record count */}
      <span style={styles.countLabel}>
        {total === 0 ? 'Kayıt yok' : `${from}–${to} / ${total} kayıt`}
      </span>

      {/* Page controls */}
      <div style={styles.controls}>
        <button
          style={styles.btn}
          onClick={() => onPageChange(1)}
          disabled={page <= 1}
          title="İlk sayfa"
          aria-label="İlk sayfa"
        >
          «
        </button>
        <button
          style={styles.btn}
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          title="Önceki sayfa"
          aria-label="Önceki sayfa"
        >
          ‹
        </button>

        <span style={styles.pageInfo}>
          {page} / {totalPages}
        </span>

        <button
          style={styles.btn}
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          title="Sonraki sayfa"
          aria-label="Sonraki sayfa"
        >
          ›
        </button>
        <button
          style={styles.btn}
          onClick={() => onPageChange(totalPages)}
          disabled={page >= totalPages}
          title="Son sayfa"
          aria-label="Son sayfa"
        >
          »
        </button>
      </div>

      {/* Page size selector */}
      {onLimitChange && (
        <select
          style={styles.select}
          value={limit}
          onChange={(e) => onLimitChange(Number(e.target.value))}
          aria-label="Sayfa boyutu"
        >
          {pageSizes.map((s) => (
            <option key={s} value={s}>
              {s} / sayfa
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

const styles = {
  container: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '10px 0',
    flexWrap: 'wrap',
  },
  countLabel: {
    fontSize: '13px',
    color: 'var(--text-muted, #888)',
    minWidth: '120px',
  },
  controls: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  btn: {
    background: 'var(--bg-secondary, #f3f4f6)',
    border: '1px solid var(--border, #e5e7eb)',
    borderRadius: '6px',
    padding: '4px 10px',
    cursor: 'pointer',
    fontSize: '14px',
    color: 'var(--text-primary, #374151)',
    transition: 'background 0.15s',
    minWidth: '32px',
  },
  pageInfo: {
    fontSize: '13px',
    color: 'var(--text-primary, #374151)',
    padding: '0 8px',
    fontWeight: 500,
  },
  select: {
    background: 'var(--bg-secondary, #f3f4f6)',
    border: '1px solid var(--border, #e5e7eb)',
    borderRadius: '6px',
    padding: '4px 8px',
    fontSize: '13px',
    color: 'var(--text-primary, #374151)',
    cursor: 'pointer',
  },
};
