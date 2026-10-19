import { describe, expect, it } from 'vitest';
import { mergePaceSeries } from '../forecastReports';

describe('pace curve alignment', () => {
  it('keeps a comparison curve even without any current reservations', () => {
    expect(mergePaceSeries([], [{ days_out: 2, rooms_on_books: 3 }])).toEqual([{ days_out: 2, bu_yil: null, karsilastirma: 3 }]);
  });

  it('uses the union and step values, not a current-only axis or interpolation', () => {
    expect(mergePaceSeries([{ days_out: 10, rooms_on_books: 1 }, { days_out: 0, rooms_on_books: 3 }],
      [{ days_out: 20, rooms_on_books: 2 }, { days_out: 5, rooms_on_books: 4 }, { days_out: 0, rooms_on_books: 5 }])).toEqual([
      { days_out: 20, bu_yil: 0, karsilastirma: 2 },
      { days_out: 10, bu_yil: 1, karsilastirma: 2 },
      { days_out: 5, bu_yil: 1, karsilastirma: 4 },
      { days_out: 0, bu_yil: 3, karsilastirma: 5 },
    ]);
  });

  it('leaves the not-yet-observed part of the current curve unavailable', () => {
    expect(mergePaceSeries([{ days_out: 10, rooms_on_books: 1 }], [{ days_out: 0, rooms_on_books: 5 }])).toEqual([
      { days_out: 10, bu_yil: 1, karsilastirma: 0 }, { days_out: 0, bu_yil: null, karsilastirma: 5 },
    ]);
  });
});
