// @vitest-environment node
import { describe, it, expect, beforeAll } from 'vitest';
import request from 'supertest';
import { appPromise } from '../server.js';
import type { Express } from 'express';

// Setup environment variable before importing server
process.env.NODE_ENV = 'test';
process.env.ADMIN_USERNAME = 'admin';
process.env.ADMIN_PASSWORD = 'password';
const authHeader = 'Basic ' + Buffer.from('admin:password').toString('base64');

describe('Security Headers', () => {
  it('should set essential security headers and hide X-Powered-By', async () => {
    const response = await request(app).get('/api/health').set('Authorization', authHeader);
    expect(response.headers['x-powered-by']).toBeUndefined();
    expect(response.headers['x-content-type-options']).toBe('nosniff');
    expect(response.headers['x-frame-options']).toBe('DENY');
    expect(response.headers['x-xss-protection']).toBe('1; mode=block');
    expect(response.headers['strict-transport-security']).toBe('max-age=31536000; includeSubDomains');
    expect(response.headers['referrer-policy']).toBe('strict-origin-when-cross-origin');
    expect(response.headers['cache-control']).toBe('no-store');
    expect(response.headers['content-security-policy']).toBe("default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https: http:; font-src 'self' data: https: http:; connect-src 'self'");
  });
});

let app: Express;

beforeAll(async () => {
    app = await appPromise;
});

describe('POST /api/products security validation', () => {
  it('should return 400 when required fields are missing', async () => {
    const response = await request(app)
      .post('/api/products')
      .set('Authorization', authHeader)
      .send({
        name: 'Product Name',
        category: 'Test Category',
        // Missing code, unit, price_ex_gst, gst_rate, hsn_code
      });

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invalid or missing required fields');
  });

  it('should return 400 when price_ex_gst is not a number', async () => {
    const response = await request(app)
      .post('/api/products')
      .set('Authorization', authHeader)
      .send({
        code: 'PROD001',
        name: 'Product Name',
        category: 'Test Category',
        unit: 'kg',
        price_ex_gst: '100', // Invalid: should be a number
        gst_rate: 18,
        hsn_code: '123456',
      });

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invalid or missing required fields');
  });

  it('should return 400 when stock is provided but is not a number', async () => {
    const response = await request(app)
      .post('/api/products')
      .set('Authorization', authHeader)
      .send({
        code: 'PROD001',
        name: 'Product Name',
        category: 'Test Category',
        unit: 'kg',
        price_ex_gst: 100,
        gst_rate: 18,
        hsn_code: '123456',
        stock: '50', // Invalid: should be a number
      });

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invalid or missing required fields');
  });
});

describe('PUT /api/settings security validation', () => {
  it('should return 400 when store_name is not a string', async () => {
    const response = await request(app)
      .put('/api/settings')
      .set('Authorization', authHeader)
      .send({
        store_name: 123, // Invalid: should be string
        address: 'Test Address',
        phone: '1234567890',
        gstin: 'GSTIN123',
        state_code: 'SC123',
        logo_url: 'http://example.com/logo.png'
      });

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invalid or missing required fields');
  });

  it('should return 400 when logo_url is not a string or null', async () => {
    const response = await request(app)
      .put('/api/settings')
      .set('Authorization', authHeader)
      .send({
        store_name: 'Store Name',
        address: 'Test Address',
        phone: '1234567890',
        gstin: 'GSTIN123',
        state_code: 'SC123',
        logo_url: 123 // Invalid: should be string or null
      });

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invalid or missing required fields');
  });

  it('should return 400 when required fields are missing', async () => {
    const response = await request(app)
      .put('/api/settings')
      .set('Authorization', authHeader)
      .send({
        store_name: 'Store Name'
        // Missing other fields
      });

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invalid or missing required fields');
  });

  it('should return 413 Payload Too Large when request body exceeds 1MB', async () => {
    const largeString = 'a'.repeat(1024 * 1024 * 2); // 2MB string
    const response = await request(app)
      .put('/api/settings')
      .set('Authorization', authHeader)
      .send({
        store_name: largeString,
        address: 'Test Address',
        phone: '1234567890',
        gstin: 'GSTIN123',
        state_code: 'SC123',
        logo_url: 'http://example.com/logo.png'
      });

    expect(response.status).toBe(413);
  });
});
