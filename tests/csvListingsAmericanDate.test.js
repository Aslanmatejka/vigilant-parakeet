/**
 * CSV bulk_import_listings — American date format regressions (Jest)
 *
 * Donors typing MM/DD/YYYY into an Excel/Sheets CSV used to be silently
 * overwritten with a category default because sanitizeListingExpiry only
 * accepted ISO. parseListingsCsv now routes cells through parseAmericanDate
 * so the donor's real date survives all the way to the backend / DB.
 */
import {
  parseAmericanDate,
  parseListingsCsv,
  downloadCsvTemplate,
  sanitizeListingExpiry,
} from '../utils/csvListings.js';

describe('parseAmericanDate', () => {
  it('parses MM/DD/YYYY', () => {
    expect(parseAmericanDate('9/1/2026')).toBe('2026-09-01');
    expect(parseAmericanDate('09/01/2026')).toBe('2026-09-01');
    expect(parseAmericanDate('12/31/2027')).toBe('2027-12-31');
  });

  it('parses M-D-YYYY (US hyphenated)', () => {
    expect(parseAmericanDate('9-1-2026')).toBe('2026-09-01');
  });

  it('expands 2-digit year into 2000s', () => {
    expect(parseAmericanDate('9/1/26')).toBe('2026-09-01');
  });

  it('passes ISO YYYY-MM-DD through unchanged', () => {
    expect(parseAmericanDate('2026-09-01')).toBe('2026-09-01');
  });

  it('rejects impossible calendar dates', () => {
    expect(parseAmericanDate('13/1/2026')).toBeNull();
    expect(parseAmericanDate('2/30/2026')).toBeNull();
  });

  it('returns null for empty / garbage', () => {
    expect(parseAmericanDate('')).toBeNull();
    expect(parseAmericanDate(null)).toBeNull();
    expect(parseAmericanDate('banana')).toBeNull();
  });
});

describe('parseListingsCsv expiry_date column', () => {
  const iso = (mmddyyyy) => parseAmericanDate(mmddyyyy);

  it('converts American MM/DD/YYYY cells to ISO', () => {
    const csv = [
      'title,quantity,unit,category,expiry_date',
      'Apples,5,lbs,produce,9/15/2027',
    ].join('\n');
    const { rows, errors } = parseListingsCsv(csv);
    expect(errors).toEqual([]);
    expect(rows).toHaveLength(1);
    expect(rows[0].expiry_date).toBe('2027-09-15');
  });

  it('preserves ISO YYYY-MM-DD passthrough', () => {
    const csv = [
      'title,quantity,unit,category,expiry_date',
      'Apples,5,lbs,produce,2027-09-15',
    ].join('\n');
    const { rows } = parseListingsCsv(csv);
    expect(rows[0].expiry_date).toBe('2027-09-15');
  });

  it('falls back to category default when the cell is garbage', () => {
    const csv = [
      'title,quantity,unit,category,expiry_date',
      'Apples,5,lbs,produce,banana',
    ].join('\n');
    const { rows } = parseListingsCsv(csv);
    // Garbage cells still get soft-defaulted so imports don't break.
    expect(rows[0].expiry_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(rows[0].expiry_date).not.toBe('banana');
  });

  it('past US date still falls back to a category default (via sanitizeListingExpiry)', () => {
    const csv = [
      'title,quantity,unit,category,expiry_date',
      'Apples,5,lbs,produce,1/1/2000',
    ].join('\n');
    const { rows } = parseListingsCsv(csv);
    // Parser converts to ISO, sanitizeListingExpiry then replaces because past.
    expect(rows[0].expiry_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(rows[0].expiry_date).not.toBe('2000-01-01');
  });
});

describe('sanitizeListingExpiry with parseAmericanDate output', () => {
  it('accepts the ISO output of parseAmericanDate as-is', () => {
    const isoFuture = new Date();
    isoFuture.setFullYear(isoFuture.getFullYear() + 1);
    const mm = String(isoFuture.getMonth() + 1).padStart(2, '0');
    const dd = String(isoFuture.getDate()).padStart(2, '0');
    const yyyy = isoFuture.getFullYear();
    const usDate = `${mm}/${dd}/${yyyy}`;
    const iso = parseAmericanDate(usDate);
    const row = sanitizeListingExpiry({ category: 'produce', expiry_date: iso });
    expect(row.expiry_date).toBe(iso);
  });
});

describe('downloadCsvTemplate uses American MM/DD/YYYY', () => {
  it('writes at least one example row cell in MM/DD/YYYY', () => {
    // jsdom's Blob doesn't implement .text() reliably in older test envs,
    // so capture the raw CSV string from the Blob constructor's first arg.
    let capturedText = '';
    const OriginalBlob = global.Blob;
    global.Blob = function MockBlob(parts) {
      capturedText = Array.isArray(parts) ? parts.join('') : String(parts || '');
      return { size: capturedText.length, type: 'text/csv' };
    };
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = () => 'blob:mock';
    URL.revokeObjectURL = () => {};

    const origCreate = document.createElement.bind(document);
    const spy = jest.spyOn(document, 'createElement').mockImplementation((tag) => {
      const el = origCreate(tag);
      if (tag === 'a') el.click = () => {};
      return el;
    });

    try {
      downloadCsvTemplate();
      expect(capturedText).not.toBe('');
      const cells = capturedText.split(/[\r\n,]/);
      const usCells = cells.filter((c) => /^\d{1,2}\/\d{1,2}\/\d{4}$/.test(c.trim()));
      expect(usCells.length).toBeGreaterThanOrEqual(1);
      const isoCells = cells.filter((c) => /^\d{4}-\d{2}-\d{2}$/.test(c.trim()));
      expect(isoCells.length).toBe(0);
    } finally {
      global.Blob = OriginalBlob;
      URL.createObjectURL = originalCreateObjectURL;
      URL.revokeObjectURL = originalRevokeObjectURL;
      spy.mockRestore();
    }
  });
});
