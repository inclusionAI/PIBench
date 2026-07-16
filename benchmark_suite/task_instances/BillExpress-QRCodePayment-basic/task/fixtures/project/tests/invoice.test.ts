import { describe, it, expect, beforeEach } from 'vitest';
import Database from 'better-sqlite3';
import { getNextInvoiceNumber } from '../src/utils/invoice.js';

describe('getNextInvoiceNumber', () => {
  let db: any;

  beforeEach(() => {
    db = new Database(':memory:');
    db.exec(`
      CREATE TABLE invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number TEXT UNIQUE NOT NULL
      )
    `);
  });

  it('should generate first invoice number for a fiscal year (April)', () => {
    const date = new Date('2024-04-01');
    const result = getNextInvoiceNumber(db, date);
    expect(result).toBe('RAC/2024-25/00001');
  });

  it('should generate first invoice number for a fiscal year (March - previous year)', () => {
    const date = new Date('2025-03-31');
    const result = getNextInvoiceNumber(db, date);
    expect(result).toBe('RAC/2024-25/00001');
  });

  it('should increment invoice number within the same fiscal year', () => {
    const date = new Date('2024-05-15');
    db.prepare('INSERT INTO invoices (invoice_number) VALUES (?)').run('RAC/2024-25/00001');

    const result = getNextInvoiceNumber(db, date);
    expect(result).toBe('RAC/2024-25/00002');
  });

  it('should handle multiple existing invoices and pick the next number', () => {
    const date = new Date('2024-05-15');
    db.prepare('INSERT INTO invoices (invoice_number) VALUES (?)').run('RAC/2024-25/00001');
    db.prepare('INSERT INTO invoices (invoice_number) VALUES (?)').run('RAC/2024-25/00002');
    db.prepare('INSERT INTO invoices (invoice_number) VALUES (?)').run('RAC/2024-25/00041');

    const result = getNextInvoiceNumber(db, date);
    expect(result).toBe('RAC/2024-25/00042');
  });

  it('should reset sequence for a new fiscal year', () => {
    // Existing invoice for FY 2023-24
    db.prepare('INSERT INTO invoices (invoice_number) VALUES (?)').run('RAC/2023-24/00010');

    // Request for FY 2024-25
    const date = new Date('2024-04-01');
    const result = getNextInvoiceNumber(db, date);
    expect(result).toBe('RAC/2024-25/00001');
  });

  it('should handle non-numeric sequence parts gracefully', () => {
    db.prepare('INSERT INTO invoices (invoice_number) VALUES (?)').run('RAC/2024-25/ABC');
    const date = new Date('2024-05-15');
    const result = getNextInvoiceNumber(db, date);
    expect(result).toBe('RAC/2024-25/00001');
  });
});
