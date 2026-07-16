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
    // clear db
    db.exec('DELETE FROM invoice_items');
    db.exec('DELETE FROM invoices');
    db.exec('DELETE FROM products');
});

describe('Products API', () => {
  const testProduct = {
    code: 'TEST_01',
    name: 'Test Product 1',
    category: 'Test',
    unit: 'pcs',
    price_ex_gst: 100,
    gst_rate: 18,
    hsn_code: '1234',
    stock: 10
  };

  const testProduct2 = {
    code: 'TEST_02',
    name: 'Apple',
    category: 'Fruit',
    unit: 'kg',
    price_ex_gst: 150,
    gst_rate: 0,
    hsn_code: '0000',
    stock: 20
  };

  const testProduct3 = {
    code: 'TEST_03',
    name: 'Banana',
    category: 'Fruit',
    unit: 'kg',
    price_ex_gst: 50,
    gst_rate: 0,
    hsn_code: '0000',
    stock: 30
  };

  describe('GET /api/products', () => {
    it('should return empty list when no products exist', async () => {
      const response = await request(app).get('/api/products').set('Authorization', authHeader);
      expect(response.status).toBe(200);
      expect(response.body).toEqual({ data: [], total: 0 });
    });

    it('should return products sorted by name ASC', async () => {
      const insertProduct = db.prepare('INSERT INTO products (code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
      insertProduct.run(testProduct.code, testProduct.name, testProduct.category, testProduct.unit, testProduct.price_ex_gst, testProduct.gst_rate, testProduct.hsn_code, testProduct.stock);
      insertProduct.run(testProduct3.code, testProduct3.name, testProduct3.category, testProduct3.unit, testProduct3.price_ex_gst, testProduct3.gst_rate, testProduct3.hsn_code, testProduct3.stock);
      insertProduct.run(testProduct2.code, testProduct2.name, testProduct2.category, testProduct2.unit, testProduct2.price_ex_gst, testProduct2.gst_rate, testProduct2.hsn_code, testProduct2.stock);

      const response = await request(app).get('/api/products').set('Authorization', authHeader);
      expect(response.status).toBe(200);
      expect(response.body.data.length).toBe(3);

      // Order should be Apple, Banana, Test Product 1
      expect(response.body.data[0].name).toBe('Apple');
      expect(response.body.data[1].name).toBe('Banana');
      expect(response.body.data[2].name).toBe('Test Product 1');
    });
  });

  describe('POST /api/products', () => {
    it('should create a valid product', async () => {
      const response = await request(app)
        .post('/api/products')
        .set('Authorization', authHeader)
        .send(testProduct);

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('id');

      const product = db.prepare('SELECT * FROM products WHERE id = ?').get(response.body.id) as any;
      expect(product).toBeTruthy();
      expect(product.code).toBe(testProduct.code);
      expect(product.stock).toBe(testProduct.stock);
    });

    it('should default stock to 0 if not provided', async () => {
      const { stock, ...productWithoutStock } = testProduct;
      const response = await request(app)
        .post('/api/products')
        .set('Authorization', authHeader)
        .send(productWithoutStock);

      expect(response.status).toBe(200);

      const product = db.prepare('SELECT * FROM products WHERE id = ?').get(response.body.id) as any;
      expect(product.stock).toBe(0);
    });

    it('should return 400 when missing required fields', async () => {
      const { name, ...invalidProduct } = testProduct;
      const response = await request(app)
        .post('/api/products')
        .set('Authorization', authHeader)
        .send(invalidProduct);

      expect(response.status).toBe(400);
      expect(response.body.error).toBe('Invalid or missing required fields');
    });

    it('should return 400 when field types are invalid', async () => {
      const invalidProduct = { ...testProduct, price_ex_gst: '100' }; // price should be number
      const response = await request(app)
        .post('/api/products')
        .set('Authorization', authHeader)
        .send(invalidProduct);

      expect(response.status).toBe(400);
      expect(response.body.error).toBe('Invalid or missing required fields');
    });

    it('should return 400 when inserting a product with a duplicate code', async () => {
      const res1 = await request(app)
        .post('/api/products')
        .set('Authorization', authHeader)
        .send(testProduct);
      expect(res1.status).toBe(200);

      const res2 = await request(app)
        .post('/api/products')
        .set('Authorization', authHeader)
        .send(testProduct);

      expect(res2.status).toBe(400);
      expect(res2.body.error).toBe('An error occurred while processing the request');
    });
  });

  describe('PUT /api/products/:id', () => {
    it('should update an existing product', async () => {
      // Create a product first
      const insertResponse = await request(app)
        .post('/api/products')
        .set('Authorization', authHeader)
        .send(testProduct);

      const id = insertResponse.body.id;

      const updatedProduct = {
        ...testProduct,
        name: 'Updated Product Name',
        price_ex_gst: 200,
        stock: 50
      };

      const updateResponse = await request(app)
        .put(`/api/products/${id}`)
        .set('Authorization', authHeader)
        .send(updatedProduct);

      expect(updateResponse.status).toBe(200);
      expect(updateResponse.body.success).toBe(true);

      const product = db.prepare('SELECT * FROM products WHERE id = ?').get(id) as any;
      expect(product.name).toBe('Updated Product Name');
      expect(product.price_ex_gst).toBe(200);
      expect(product.stock).toBe(50);
    });

    it('should return 400 when invalid fields are provided for update', async () => {
      const insertResponse = await request(app)
        .post('/api/products')
        .set('Authorization', authHeader)
        .send(testProduct);

      const id = insertResponse.body.id;

      const updatedProduct = {
        ...testProduct,
        price_ex_gst: '200' // Should be a number
      };

      const updateResponse = await request(app)
        .put(`/api/products/${id}`)
        .set('Authorization', authHeader)
        .send(updatedProduct);

      expect(updateResponse.status).toBe(400);
      expect(updateResponse.body.error).toBe('Invalid or missing required fields');
    });
  });

  describe('DELETE /api/products/:id', () => {
    it('should delete a product', async () => {
      // Create a product first
      const insertResponse = await request(app)
        .post('/api/products')
        .set('Authorization', authHeader)
        .send(testProduct);

      const id = insertResponse.body.id;

      const deleteResponse = await request(app)
        .delete(`/api/products/${id}`)
        .set('Authorization', authHeader);

      expect(deleteResponse.status).toBe(200);
      expect(deleteResponse.body.success).toBe(true);

      const product = db.prepare('SELECT * FROM products WHERE id = ?').get(id);
      expect(product).toBeUndefined();
    });
  });
});
