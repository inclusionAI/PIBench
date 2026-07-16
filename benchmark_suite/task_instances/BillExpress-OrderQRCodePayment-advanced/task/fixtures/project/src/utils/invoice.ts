
import type { Database } from 'better-sqlite3';

/**
 * Generates the next invoice number based on the Indian Fiscal Year (April to March).
 * Format: RAC/YYYY-YY/XXXXX
 *
 * @param db The better-sqlite3 database instance
 * @param date The date to use for fiscal year calculation (defaults to now)
 * @returns The next invoice number
 */
export function getNextInvoiceNumber(db: Database, date: Date = new Date()): string {
  const month = date.getMonth(); // 0-indexed, 0 = Jan, 3 = April
  let startYear = date.getFullYear();

  // Indian Fiscal Year starts from April
  if (month < 3) { // Jan, Feb, Mar
    startYear -= 1;
  }

  const endYear = (startYear + 1).toString().slice(-2);
  const prefix = `RAC/${startYear}-${endYear}/`;

  const lastInvoice = db.prepare(
    "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ? ORDER BY id DESC LIMIT 1"
  ).get(`${prefix}%`) as { invoice_number: string } | undefined;

  let nextNumber = 1;
  if (lastInvoice) {
    const parts = lastInvoice.invoice_number.split('/');
    const lastNumPart = parts[parts.length - 1];
    const parsed = parseInt(lastNumPart, 10);
    if (!isNaN(parsed)) {
      nextNumber = parsed + 1;
    }
  }

  return `${prefix}${nextNumber.toString().padStart(5, '0')}`;
}
