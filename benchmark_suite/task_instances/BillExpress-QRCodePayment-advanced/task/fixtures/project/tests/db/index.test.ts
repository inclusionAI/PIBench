import { describe, it, expect, beforeAll } from 'vitest';

describe('Database Schema Initialization', () => {
  let db: any;

  beforeAll(async () => {
    // Set NODE_ENV to test to use an in-memory database
    process.env.NODE_ENV = 'test';

    // Dynamically import db to ensure the env var is picked up
    const module = await import('../../src/db/index.js');
    db = module.default;
  });

  const getTableInfo = (tableName: string) => {
    return db.pragma(`table_info(${tableName})`);
  };

  it('should create the users table with correct columns', () => {
    const columns = getTableInfo('users');
    const columnNames = columns.map((col: any) => col.name);

    expect(columnNames).toContain('id');
    expect(columnNames).toContain('username');
    expect(columnNames).toContain('password');
    expect(columnNames).toContain('role');
  });

  it('should create the products table with correct columns including altered ones', () => {
    const columns = getTableInfo('products');
    const columnNames = columns.map((col: any) => col.name);

    expect(columnNames).toContain('id');
    expect(columnNames).toContain('code');
    expect(columnNames).toContain('name');
    expect(columnNames).toContain('category');
    expect(columnNames).toContain('unit');
    expect(columnNames).toContain('price_ex_gst');
    expect(columnNames).toContain('gst_rate');
    expect(columnNames).toContain('hsn_code');
    // Altered column
    expect(columnNames).toContain('stock');
  });

  it('should create the customers table with correct columns including altered ones', () => {
    const columns = getTableInfo('customers');
    const columnNames = columns.map((col: any) => col.name);

    expect(columnNames).toContain('id');
    expect(columnNames).toContain('name');
    expect(columnNames).toContain('mobile');
    expect(columnNames).toContain('address');
    expect(columnNames).toContain('gstin');
    // Altered column
    expect(columnNames).toContain('state');
  });

  it('should create the invoices table with correct columns including altered ones', () => {
    const columns = getTableInfo('invoices');
    const columnNames = columns.map((col: any) => col.name);

    expect(columnNames).toContain('id');
    expect(columnNames).toContain('invoice_number');
    expect(columnNames).toContain('date');
    expect(columnNames).toContain('customer_id');
    expect(columnNames).toContain('type');
    expect(columnNames).toContain('subtotal');
    expect(columnNames).toContain('discount');
    expect(columnNames).toContain('cgst_total');
    expect(columnNames).toContain('sgst_total');
    expect(columnNames).toContain('grand_total');

    // Altered columns
    expect(columnNames).toContain('igst_total');
    expect(columnNames).toContain('status');
    expect(columnNames).toContain('payment_status');
    expect(columnNames).toContain('amount_paid');
  });

  it('should create the invoice_items table with correct columns including altered ones', () => {
    const columns = getTableInfo('invoice_items');
    const columnNames = columns.map((col: any) => col.name);

    expect(columnNames).toContain('id');
    expect(columnNames).toContain('invoice_id');
    expect(columnNames).toContain('product_id');
    expect(columnNames).toContain('product_name');
    expect(columnNames).toContain('product_code');
    expect(columnNames).toContain('hsn_code');
    expect(columnNames).toContain('unit');
    expect(columnNames).toContain('quantity');
    expect(columnNames).toContain('price_ex_gst');
    expect(columnNames).toContain('gst_rate');
    expect(columnNames).toContain('cgst_amount');
    expect(columnNames).toContain('sgst_amount');
    expect(columnNames).toContain('total');

    // Altered column
    expect(columnNames).toContain('igst_amount');
  });

  it('should create the settings table and insert default settings', () => {
    const columns = getTableInfo('settings');
    const columnNames = columns.map((col: any) => col.name);

    expect(columnNames).toContain('id');
    expect(columnNames).toContain('store_name');
    expect(columnNames).toContain('address');
    expect(columnNames).toContain('phone');
    expect(columnNames).toContain('gstin');
    expect(columnNames).toContain('state_code');
    expect(columnNames).toContain('logo_url');

    const settingsCount = db.prepare('SELECT count(*) as c FROM settings').get() as { c: number };
    expect(settingsCount.c).toBe(1);

    const settings = db.prepare('SELECT * FROM settings LIMIT 1').get();
    expect(settings.store_name).toBe('Bill Express');
    expect(settings.gstin).toBe('19AAAAA0000A1Z5');
  });

  it('should insert default sample products', () => {
    const productsCount = db.prepare('SELECT count(*) as c FROM products').get() as { c: number };
    expect(productsCount.c).toBeGreaterThan(0);

    const sampleProduct = db.prepare('SELECT * FROM products WHERE code = ?').get('UR46');
    expect(sampleProduct).toBeDefined();
    expect(sampleProduct.name).toBe('Urea 46%');
    expect(sampleProduct.stock).toBe(100);
  });
});
