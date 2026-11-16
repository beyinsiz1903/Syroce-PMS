import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import DepartmentTaxReview, { missingDepartmentSource } from './DepartmentTaxReview';
vi.mock('axios', () => ({ default: { post: vi.fn() } }));
const source = { id: 'source', charge_category: 'parking', description: 'Otopark', total: 150, currency: 'TRY' };
beforeEach(() => axios.post.mockReset());
it('requires explicit inputs and binds apply to the reviewed payload; edits invalidate approval', async () => {
  const onApplied = vi.fn();
  axios.post.mockResolvedValueOnce({ data: { source_id: 'source', run_id: 'run', preview_hash: 'a'.repeat(64), gross: 150, net: 125, vat: 25 } })
    .mockResolvedValueOnce({ data: { status: 'applied', review_id: 'receipt' } });
  render(<DepartmentTaxReview runId="run" source={source} onApplied={onApplied} />);
  fireEvent.click(screen.getByText('Vergi ayrımını önizle'));
  expect(axios.post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Toplama dahil KDV oranı (%)'), { target: { value: '20' } });
  fireEvent.change(screen.getByLabelText('Vergi kararının dayanağı'), { target: { value: 'Synthetic user-approved VAT20' } });
  fireEvent.click(screen.getByText('Vergi ayrımını önizle'));
  fireEvent.click(await screen.findByText('Bu vergi ayrımını kaydet'));
  await screen.findByText('Vergi ayrımını önizle');
  expect(axios.post).toHaveBeenLastCalledWith(expect.stringContaining('/run/tax-review/apply'), {
    source_id: 'source', vat_rate: '20', reference: 'Synthetic user-approved VAT20', expected_preview_hash: 'a'.repeat(64),
  });
});
it('only offers parking review for a structured missing-tax rejection', () => {
  expect(missingDepartmentSource('Unknown source tax must be resolved, not assumed zero: ' + JSON.stringify(source))).toEqual(source);
  const tour = { ...source, charge_category: 'concierge', total: 600 };
  expect(missingDepartmentSource('Unknown source tax must be resolved, not assumed zero: ' + JSON.stringify(tour))).toEqual(tour);
  expect(missingDepartmentSource('Other error ' + JSON.stringify(source))).toBeNull();
  expect(missingDepartmentSource('Unknown source tax must be resolved, not assumed zero: invalid')).toBeNull();
});
