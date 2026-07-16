// @vitest-environment node
import { describe, it, expect, beforeEach, beforeAll } from 'vitest';
import request from 'supertest';
import db from '../src/db/index.js';

process.env.NODE_ENV = 'test';
process.env.ADMIN_USERNAME = 'admin';
process.env.ADMIN_PASSWORD = 'password';
const authHeader = 'Basic ' + Buffer.from('admin:password').toString('base64');

import { appPromise } from '../server.js';
import type { Express } from 'express';

let app: Express;

beforeAll(async () => {
    app = await appPromise;
});

beforeEach(() => {
    db.exec('DELETE FROM invoice_items');
    db.exec('DELETE FROM invoices');
    db.exec('DELETE FROM products');
    db.exec('DELETE FROM customers');
});

describe('PUT /api/invoices/:id/cancel', () => {
  let customerId: number;
  let p1Id: number;
  let p2Id: number;
  let activeInvoiceId: number;
  let cancelledInvoiceId: number;

  beforeEach(() => {
    // Seed Customer
    const insertCustomer = db.prepare('INSERT INTO customers (name, mobile) VALUES (?, ?)');
    const cInfo = insertCustomer.run('Test Customer', '1234567890');
    customerId = cInfo.lastInsertRowid as number;

    // Seed Products with initial stock
    const insertProduct = db.prepare('INSERT INTO products (code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    const p1Info = insertProduct.run('P1', 'Product 1', 'Cat', 'Unit', 100, 18, '1234', 100);
    const p2Info = insertProduct.run('P2', 'Product 2', 'Cat', 'Unit', 200, 18, '1234', 50);
    p1Id = p1Info.lastInsertRowid as number;
    p2Id = p2Info.lastInsertRowid as number;

    // Seed Active Invoice
    const insertInvoice = db.prepare(`INSERT INTO invoices (invoice_number, customer_id, type, subtotal, discount, cgst_total, sgst_total, grand_total, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`);
    const i1Info = insertInvoice.run('INV-1001', customerId, 'b2b', 1000, 0, 90, 90, 1180, 'active');
    activeInvoiceId = i1Info.lastInsertRowid as number;

    // Seed Cancelled Invoice
    const i2Info = insertInvoice.run('INV-1002', customerId, 'b2b', 500, 0, 45, 45, 590, 'cancelled');
    cancelledInvoiceId = i2Info.lastInsertRowid as number;

    // Seed Invoice Items for Active Invoice
    const insertItem = db.prepare('INSERT INTO invoice_items (invoice_id, product_id, product_name, product_code, hsn_code, unit, quantity, price_ex_gst, gst_rate, cgst_amount, sgst_amount, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)');
    // 10 quantity of P1, 5 quantity of P2
    insertItem.run(activeInvoiceId, p1Id, 'Product 1', 'P1', '1234', 'Unit', 10, 100, 18, 90, 90, 1180);
    insertItem.run(activeInvoiceId, p2Id, 'Product 2', 'P2', '1234', 'Unit', 5, 200, 18, 45, 45, 590);
  });

  it('should successfully cancel an active invoice and restore stock', async () => {
    // Check initial stock
    const p1Before = db.prepare('SELECT stock FROM products WHERE id = ?').get(p1Id) as { stock: number };
    const p2Before = db.prepare('SELECT stock FROM products WHERE id = ?').get(p2Id) as { stock: number };
    expect(p1Before.stock).toBe(100);
    expect(p2Before.stock).toBe(50);

    const response = await request(app)
      .put(`/api/invoices/${activeInvoiceId}/cancel`)
      .set('Authorization', authHeader);

    expect(response.status).toBe(200);
    expect(response.body.success).toBe(true);

    // Verify invoice status is 'cancelled'
    const invoice = db.prepare('SELECT status FROM invoices WHERE id = ?').get(activeInvoiceId) as { status: string };
    expect(invoice.status).toBe('cancelled');

    // Verify stock is restored
    // P1: 100 + 10 = 110
    // P2: 50 + 5 = 55
    const p1After = db.prepare('SELECT stock FROM products WHERE id = ?').get(p1Id) as { stock: number };
    const p2After = db.prepare('SELECT stock FROM products WHERE id = ?').get(p2Id) as { stock: number };
    expect(p1After.stock).toBe(110);
    expect(p2After.stock).toBe(55);
  });

  it('should return 400 when trying to cancel an already cancelled invoice', async () => {
    const response = await request(app)
      .put(`/api/invoices/${cancelledInvoiceId}/cancel`)
      .set('Authorization', authHeader);

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invoice not found or already cancelled');
  });

  it('should return 400 when trying to cancel a non-existent invoice', async () => {
    const response = await request(app)
      .put('/api/invoices/99999/cancel')
      .set('Authorization', authHeader);

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invoice not found or already cancelled');
  });
});
