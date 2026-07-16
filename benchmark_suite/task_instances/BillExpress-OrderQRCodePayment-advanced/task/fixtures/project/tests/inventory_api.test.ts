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
    db.exec('DELETE FROM inventory_transactions');
    db.exec('DELETE FROM products');
});

describe('Inventory API', () => {
  let productId: number;

  beforeEach(() => {
    const insertProduct = db.prepare('INSERT INTO products (code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    const pInfo = insertProduct.run('P1', 'Product 1', 'Cat', 'Unit', 100, 18, '1234', 100);
    productId = pInfo.lastInsertRowid as number;
  });

  it('should fetch stock transactions for a product', async () => {
    db.prepare('INSERT INTO inventory_transactions (product_id, type, quantity, reason) VALUES (?, ?, ?, ?)').run(productId, 'restock', 50, 'Initial restock');
    
    const response = await request(app)
      .get(`/api/products/${productId}/transactions`)
      .set('Authorization', authHeader);

    expect(response.status).toBe(200);
    expect(Array.isArray(response.body)).toBe(true);
    expect(response.body.length).toBe(1);
    expect(response.body[0].type).toBe('restock');
    expect(response.body[0].quantity).toBe(50);
  });

  it('should adjust stock and record transaction', async () => {
    const adjustmentData = {
      type: 'restock',
      quantity: 20,
      reason: 'Manual addition'
    };

    const response = await request(app)
      .post(`/api/products/${productId}/stock-adjustment`)
      .set('Authorization', authHeader)
      .send(adjustmentData);

    expect(response.status).toBe(200);
    expect(response.body.success).toBe(true);
    expect(response.body.newStock).toBe(120);

    // Verify stock in DB
    const product = db.prepare('SELECT stock FROM products WHERE id = ?').get(productId) as { stock: number };
    expect(product.stock).toBe(120);

    // Verify transaction recorded
    const transactions = db.prepare('SELECT * FROM inventory_transactions WHERE product_id = ?').all(productId);
    expect(transactions.length).toBe(1);
    expect(transactions[0].type).toBe('restock');
    expect(transactions[0].quantity).toBe(20);
  });

  it('should handle negative adjustments (deductions)', async () => {
    const adjustmentData = {
      type: 'damage',
      quantity: -5,
      reason: 'Broken'
    };

    const response = await request(app)
      .post(`/api/products/${productId}/stock-adjustment`)
      .set('Authorization', authHeader)
      .send(adjustmentData);

    expect(response.status).toBe(200);
    expect(response.body.newStock).toBe(95);

    const product = db.prepare('SELECT stock FROM products WHERE id = ?').get(productId) as { stock: number };
    expect(product.stock).toBe(95);
  });

  it('should reject NaN and Infinity for quantity', async () => {
    const nanResponse = await request(app)
      .post(`/api/products/${productId}/stock-adjustment`)
      .set('Authorization', authHeader)
      .send({
        type: 'restock',
        quantity: NaN,
        reason: 'NaN value'
      });

    expect(nanResponse.status).toBe(400);

    const infinityResponse = await request(app)
      .post(`/api/products/${productId}/stock-adjustment`)
      .set('Authorization', authHeader)
      .send({
        type: 'restock',
        quantity: Infinity,
        reason: 'Infinity value'
      });

    expect(infinityResponse.status).toBe(400);
  });
});
