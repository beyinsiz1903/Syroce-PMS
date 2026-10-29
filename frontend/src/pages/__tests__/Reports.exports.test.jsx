import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { toast } from 'sonner';
import Reports from '../Reports';
import { defaultReportDates, reportDownloadError, reportDownloadUrl } from '@/utils/reportExports';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'tr' } }) }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => '2026-10-07' }));
vi.mock('@/components/Layout', () => ({ default: ({ children }) => <main>{children}</main> }));
vi.mock('@/components/NightAuditModule', () => ({ default: () => null }));
vi.mock('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }) => <select aria-label="Rapor türü" defaultValue="" onChange={e => onValueChange(e.target.value)}><option value="" />{children}</select>,
  SelectTrigger: () => null, SelectValue: () => null,
  SelectContent: ({ children }) => children,
  SelectItem: ({ value }) => <option value={value}>{value}</option>,
}));

const fileResponse = { data: 'PK isolated workbook', headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' } };

function addReport(id) {
  fireEvent.click(screen.getByRole('button', { name: 'Rapor Ekle' }));
  fireEvent.change(screen.getByRole('combobox', { name: 'Rapor türü' }), { target: { value: id } });
}

beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockResolvedValue(fileResponse);
  window.URL.createObjectURL = vi.fn(() => 'blob:isolated-report');
  window.URL.revokeObjectURL = vi.fn();
  vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
});

afterEach(() => {
  if (vi.isFakeTimers()) {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  }
});

describe('Report exports', () => {
  it.each([
    ['2026-10-07', '2026-10-07', '2026-11-05'],
    ['2028-02-01', '2028-02-01', '2028-03-01'],
  ])('forecast starts at the PMS day %s, not a lookback period', (day, start, end) => {
    expect(defaultReportDates({ id: 'forecast-detail' }, day)).toEqual({ startDate: start, endDate: end, reportDate: day });
  });

  it('uses calendar-day arithmetic independent of browser UTC offset', () => {
    expect(defaultReportDates({ id: 'revenue-detail' }, '2026-01-01')).toEqual({ startDate: '2025-12-03', endDate: '2026-01-01', reportDate: '2026-01-01' });
  });

  it('binds the displayed forecast period to the download', async () => {
    render(<Reports tenant={{}} />);
    addReport('forecast-detail');
    expect(screen.getByLabelText('reports.forecastDetailReport başlangıç tarihi')).toHaveValue('2026-10-07');
    expect(screen.getByLabelText('reports.forecastDetailReport bitiş tarihi')).toHaveValue('2026-11-05');
    fireEvent.click(screen.getByRole('button', { name: 'İndir' }));
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/reports/forecast-detail/excel?start_date=2026-10-07&end_date=2026-11-05', { responseType: 'blob' }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledOnce());
  });

  it('does not send an invalid or reversed period to the server', async () => {
    render(<Reports tenant={{}} />);
    addReport('forecast-detail');
    fireEvent.change(screen.getByLabelText('reports.forecastDetailReport başlangıç tarihi'), { target: { value: '2026-12-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'İndir' }));
    expect(toast.error).toHaveBeenCalledWith('Başlangıç tarihi bitiş tarihinden sonra olamaz.');
    expect(axios.get).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('reports.forecastDetailReport başlangıç tarihi'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'İndir' }));
    expect(toast.error).toHaveBeenCalledWith('Geçerli bir rapor tarihi seçin.');
    expect(axios.get).not.toHaveBeenCalled();
  });

  it('explains incomplete-ledger errors returned as a blob instead of hiding them', async () => {
    axios.get.mockRejectedValue({ response: { data: { text: async () => JSON.stringify({ detail: 'Alacak verisi eksik; rapor oluşturulamadı.' }) } } });
    render(<Reports tenant={{}} />);
    addReport('company-aging');
    fireEvent.click(screen.getByRole('button', { name: 'İndir' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('reports.companyAgingReport: Alacak verisi eksik; rapor oluşturulamadı.'));
    expect(window.URL.createObjectURL).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('does not save an HTML login/error response with an xlsx filename', async () => {
    axios.get.mockResolvedValue({ data: '<html>Login</html>', headers: { 'content-type': 'text/html' } });
    render(<Reports tenant={{}} />);
    addReport('company-aging');
    fireEvent.click(screen.getByRole('button', { name: 'İndir' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledOnce());
    expect(window.URL.createObjectURL).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('holds one busy state for the whole batch and prevents duplicate downloads', async () => {
    let finishFirst, finishSecond;
    axios.get.mockImplementationOnce(() => new Promise(resolve => { finishFirst = resolve; }))
      .mockImplementationOnce(() => new Promise(resolve => { finishSecond = resolve; }));
    render(<Reports tenant={{}} />);
    addReport('company-aging');
    addReport('forecast-detail');
    const all = screen.getByRole('button', { name: 'reports.downloadAll' });
    fireEvent.click(all);
    expect(all).toBeDisabled();
    fireEvent.click(all);
    expect(axios.get).toHaveBeenCalledTimes(1);
    await act(async () => finishFirst(fileResponse));
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    expect(all).toBeDisabled();
    expect(screen.getByLabelText('reports.forecastDetailReport başlangıç tarihi')).toBeDisabled();
    await act(async () => finishSecond(fileResponse));
    await waitFor(() => expect(all).not.toBeDisabled());
    expect(toast.success).toHaveBeenCalledTimes(2);
  });

  it('validates single dates and preserves backend validation detail', async () => {
    expect(() => reportDownloadUrl({ endpoint: '/test', singleDateParam: 'date', reportDate: '2026-02-30' })).toThrow();
    expect(reportDownloadUrl({ endpoint: '/test', singleDateParam: 'date_str', reportDate: '2026-10-07' })).toBe('/test?date_str=2026-10-07');
    expect(await reportDownloadError({ response: { data: { detail: [{ msg: 'Invalid date' }] } } })).toBe('Invalid date');
  });

  it('releases its pending object URL and timer exactly once on unmount', async () => {
    vi.useFakeTimers();
    const { unmount } = render(<Reports tenant={{}} />);
    addReport('company-aging');
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'İndir' })));
    const revoke = window.URL.revokeObjectURL;
    expect(toast.success).toHaveBeenCalledOnce();
    expect(revoke).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(revoke).toHaveBeenCalledExactlyOnceWith('blob:isolated-report');
    expect(vi.getTimerCount()).toBe(0);
    vi.runOnlyPendingTimers();
    expect(revoke).toHaveBeenCalledOnce();
  });

  it('does not create a download or start the rest of a batch after unmount', async () => {
    let resolve;
    axios.get.mockImplementationOnce(() => new Promise(finish => { resolve = finish; }));
    const { unmount } = render(<Reports tenant={{}} />);
    addReport('company-aging');
    addReport('forecast-detail');
    fireEvent.click(screen.getByRole('button', { name: 'reports.downloadAll' }));
    expect(axios.get).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => resolve(fileResponse));
    expect(window.URL.createObjectURL).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(axios.get).toHaveBeenCalledTimes(1);
  });
});
