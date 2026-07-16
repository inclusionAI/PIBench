import { describe, it, expect, beforeAll } from 'vitest';

describe('Inventory Transactions Table', () => {
  let db: any;

  beforeAll(async () => {
    process.env.NODE_ENV = 'test';
    const module = await import('../../src/db/index.js');
    db = module.default;
  });

  const getTableInfo = (tableName: string) => {
    return db.pragma(`table_info(${tableName})`);
  };

  it('should create the inventory_transactions table with correct columns', () => {
    const columns = getTableInfo('inventory_transactions');
    const columnNames = columns.map((col: any) => col.name);

    expect(columnNames).toContain('id');
    expect(columnNames).toContain('product_id');
    expect(columnNames).toContain('type');
    expect(columnNames).toContain('quantity');
    expect(columnNames).toContain('reason');
    expect(columnNames).toContain('date');
  });

  it('should allow inserting and retrieving stock transactions', () => {
    const product = db.prepare('SELECT id FROM products LIMIT 1').get();
    expect(product).toBeDefined();

    const insert = db.prepare('INSERT INTO inventory_transactions (product_id, type, quantity, reason) VALUES (?, ?, ?, ?)');
    const result = insert.run(product.id, 'restock', 50, 'Monthly replenishment');
    
    expect(result.changes).toBe(1);
    const transactionId = result.lastInsertRowid;

    const transaction = db.prepare('SELECT * FROM inventory_transactions WHERE id = ?').get(transactionId);
    expect(transaction).toBeDefined();
    expect(transaction.product_id).toBe(product.id);
    expect(transaction.type).toBe('restock');
    expect(transaction.quantity).toBe(50);
    expect(transaction.reason).toBe('Monthly replenishment');
    expect(transaction.date).toBeDefined();
  });
});
