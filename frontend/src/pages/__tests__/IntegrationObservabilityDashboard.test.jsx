import { describe, expect, it } from 'vitest';
import { formatAuditTimestamp } from '../IntegrationObservabilityDashboard';

describe('formatAuditTimestamp', () => {
  it('keeps malformed or missing audit timestamps from breaking the table', () => {
    expect(formatAuditTimestamp(null, 'MM/dd HH:mm:ss')).toBe('—');
    expect(formatAuditTimestamp('not-a-date', 'MM/dd HH:mm:ss')).toBe('—');
  });

  it('formats a valid audit timestamp', () => {
    expect(formatAuditTimestamp('2026-10-03T09:08:07Z', 'yyyy-MM-dd')).toBe('2026-10-03');
  });
});
