// @vitest-environment node
import { describe, it, expect, beforeEach, beforeAll } from 'vitest';
import request from 'supertest';
import db from '../src/db/index.js';

// Setup environment variable before importing server
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
    // clear and seed db
    db.exec('DELETE FROM invoice_items');
    db.exec('DELETE FROM invoices');
    db.exec('DELETE FROM products');
    db.exec('DELETE FROM customers');
});

describe('GET /api/customers/count', () => {
  it('should return 0 when no customers exist', async () => {
    const response = await request(app).get('/api/customers/count').set('Authorization', authHeader);
    expect(response.status).toBe(200);
    expect(response.body).toEqual({ count: 0 });
  });

  it('should return the correct count of customers', async () => {
    const insertCustomer = db.prepare('INSERT INTO customers (name, mobile) VALUES (?, ?)');
    insertCustomer.run('Test Customer 1', '1234567890');
    insertCustomer.run('Test Customer 2', '0987654321');

    const response = await request(app).get('/api/customers/count').set('Authorization', authHeader);
    expect(response.status).toBe(200);
    expect(response.body).toEqual({ count: 2 });
  });
});

describe('GET /api/dashboard/analytics', () => {
  it('should return empty arrays when no data exists', async () => {
    const response = await request(app).get('/api/dashboard/analytics').set('Authorization', authHeader);

    expect(response.status).toBe(200);
    expect(response.body.last7Days).toEqual([]);
    expect(response.body.topProducts).toEqual([]);
    expect(response.body.lowStock).toEqual([]);
  });

  it('should return analytics data correctly', async () => {
    // Low stock product
    const insertProduct = db.prepare('INSERT INTO products (code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    const p1Info = insertProduct.run('TEST1', 'Product 1', 'Cat', 'Unit', 100, 18, '1234', 5); // Low stock
    const p2Info = insertProduct.run('TEST2', 'Product 2', 'Cat', 'Unit', 200, 18, '1234', 50); // High stock
    const p3Info = insertProduct.run('TEST3', 'Product 3', 'Cat', 'Unit', 300, 18, '1234', 0); // Very Low stock

    const p1Id = p1Info.lastInsertRowid;
    const p2Id = p2Info.lastInsertRowid;
    const p3Id = p3Info.lastInsertRowid;

    // Customer
    const insertCustomer = db.prepare('INSERT INTO customers (name, mobile) VALUES (?, ?)');
    const cInfo = insertCustomer.run('Test Customer', '1234567890');
    const cId = cInfo.lastInsertRowid;

    // Invoices and items
    // Invoice 1: Today
    const insertInvoice = db.prepare(`INSERT INTO invoices (invoice_number, customer_id, type, subtotal, discount, cgst_total, sgst_total, grand_total, status, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'))`);
    const i1Info = insertInvoice.run('INV-001', cId, 'b2b', 1000, 0, 90, 90, 1180, 'active');

    // Invoice 2: 3 days ago
    const insertInvoiceOld = db.prepare(`INSERT INTO invoices (invoice_number, customer_id, type, subtotal, discount, cgst_total, sgst_total, grand_total, status, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, date('now', '-3 days'))`);
    const i2Info = insertInvoiceOld.run('INV-002', cId, 'b2b', 500, 0, 45, 45, 590, 'active');

    // Invoice 3: Cancelled invoice (should not be counted)
    const insertInvoiceCancelled = db.prepare(`INSERT INTO invoices (invoice_number, customer_id, type, subtotal, discount, cgst_total, sgst_total, grand_total, status, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'))`);
    const i3Info = insertInvoiceCancelled.run('INV-003', cId, 'b2b', 2000, 0, 180, 180, 2360, 'cancelled');

    const i1Id = i1Info.lastInsertRowid;
    const i2Id = i2Info.lastInsertRowid;
    const i3Id = i3Info.lastInsertRowid;

    // Items
    const insertItem = db.prepare('INSERT INTO invoice_items (invoice_id, product_id, product_name, product_code, hsn_code, unit, quantity, price_ex_gst, gst_rate, cgst_amount, sgst_amount, total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)');

    insertItem.run(i1Id, p1Id, 'Product 1', 'TEST1', '1234', 'Unit', 2, 100, 18, 18, 18, 236);
    insertItem.run(i1Id, p2Id, 'Product 2', 'TEST2', '1234', 'Unit', 1, 200, 18, 36, 36, 236);

    insertItem.run(i2Id, p1Id, 'Product 1', 'TEST1', '1234', 'Unit', 3, 100, 18, 27, 27, 354);

    // cancelled invoice item
    insertItem.run(i3Id, p3Id, 'Product 3', 'TEST3', '1234', 'Unit', 5, 300, 18, 90, 90, 1770);

    const response = await request(app).get('/api/dashboard/analytics').set('Authorization', authHeader);

    expect(response.status).toBe(200);
    const data = response.body;

    // Verify last 7 days sales
    expect(data.last7Days.length).toBe(2);
    // order is ASC by date
    expect(data.last7Days[1].sales).toBe(1180); // Today's sales (cancelled not included)
    expect(data.last7Days[0].sales).toBe(590); // 3 days ago

    // Verify Top Products
    expect(data.topProducts.length).toBe(2);
    // P1 total qty = 2 + 3 = 5
    // P2 total qty = 1
    // P3 is in cancelled, should not be here
    expect(data.topProducts[0].name).toBe('Product 1');
    expect(data.topProducts[0].qty).toBe(5);
    expect(data.topProducts[0].revenue).toBe(236 + 354);

    expect(data.topProducts[1].name).toBe('Product 2');
    expect(data.topProducts[1].qty).toBe(1);
    expect(data.topProducts[1].revenue).toBe(236);

    // Verify Low Stock
    // P1 = 5, P3 = 0, P2 = 50 (should not be in low stock)
    expect(data.lowStock.length).toBe(2);
    expect(data.lowStock[0].name).toBe('Product 3');
    expect(data.lowStock[0].stock).toBe(0);
    expect(data.lowStock[1].name).toBe('Product 1');
    expect(data.lowStock[1].stock).toBe(5);
  });
});
