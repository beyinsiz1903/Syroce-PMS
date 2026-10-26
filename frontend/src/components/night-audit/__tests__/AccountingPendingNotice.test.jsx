import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import AccountingPendingNotice from '../AccountingPendingNotice';

afterEach(cleanup);
const run = { business_date: '2026-10-24', status: 'completed', gl_bridge_status: 'valuation_required', gl_bridge_error: 'Source valuation required' };
describe('AccountingPendingNotice', () => {
  it.each(['valuation_required', 'failed'])('keeps %s visible after operational close', gl_bridge_status => {
    render(<AccountingPendingNotice runs={[{ ...run, gl_bridge_status }]} />);
    expect(screen.getByRole('status')).toHaveTextContent('2026-10-24 günü kapandı; muhasebe aktarımı henüz tamamlanmadı');
    expect(screen.getByRole('status')).toHaveTextContent('Gün kapanışını tekrar çalıştırmayın.');
    expect(screen.getByRole('status')).toHaveTextContent(run.gl_bridge_error);
  });
  it('does not let a newer simulation hide a pending actual close', () => {
    render(<AccountingPendingNotice runs={[{ ...run, dry_run: true, business_date: '2026-10-25' }, run]} />);
    expect(screen.getByRole('status')).toHaveTextContent('2026-10-24');
  });
  it.each([[], [{ ...run, dry_run: true }], [{ ...run, is_dry_run: true }], [{ ...run, status: 'running' }], [{ ...run, gl_bridge_status: 'posted' }]].map(runs => [runs]))('does not invent a pending close: %j', runs => {
    render(<AccountingPendingNotice runs={runs} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
