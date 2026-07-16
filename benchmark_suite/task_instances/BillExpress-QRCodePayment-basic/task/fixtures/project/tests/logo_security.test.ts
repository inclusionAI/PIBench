//@vitest-environment node
import { describe, it, expect, beforeAll } from 'vitest';
import request from 'supertest';
import { appPromise } from '../server.js';
import type { Express } from 'express';

process.env.NODE_ENV = 'test';
process.env.ADMIN_USERNAME = 'admin';
process.env.ADMIN_PASSWORD = 'password';
const authHeader = 'Basic ' + Buffer.from('admin:password').toString('base64');

let app: Express;

beforeAll(async () => {
    app = await appPromise;
});

describe('PUT /api/settings security validation', () => {
  it('should prevent javascript URLs in logo_url', async () => {
    const response = await request(app)
      .put('/api/settings')
      .set('Authorization', authHeader)
      .send({
        store_name: 'Store',
        address: 'Test Address',
        phone: '1234567890',
        gstin: 'GSTIN123',
        state_code: 'SC123',
        logo_url: 'javascript:alert(1)'
      });

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invalid or missing required fields');
  });

  it('should prevent data URLs in logo_url', async () => {
    const response = await request(app)
      .put('/api/settings')
      .set('Authorization', authHeader)
      .send({
        store_name: 'Store',
        address: 'Test Address',
        phone: '1234567890',
        gstin: 'GSTIN123',
        state_code: 'SC123',
        logo_url: 'data:text/html,<script>alert(1)</script>'
      });

    expect(response.status).toBe(400);
    expect(response.body.error).toBe('Invalid or missing required fields');
  });
});
