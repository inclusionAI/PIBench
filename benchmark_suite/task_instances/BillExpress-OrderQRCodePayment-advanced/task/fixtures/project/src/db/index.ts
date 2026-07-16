import Database from 'better-sqlite3';
import path from 'path';
import fs from 'fs';

const dbPath = process.env.NODE_ENV === 'test' ? ':memory:' : path.resolve(process.cwd(), 'data.db');
const db = new Database(dbPath);

db.pragma('journal_mode = WAL');

// Initialize schema
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff'
  );

  CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit TEXT NOT NULL,
    price_ex_gst REAL NOT NULL,
    gst_rate REAL NOT NULL,
    hsn_code TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    mobile TEXT,
    address TEXT,
    gstin TEXT,
    state TEXT
  );

  CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT UNIQUE NOT NULL,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    customer_id INTEGER,
    type TEXT NOT NULL, -- 'cash' or 'b2b'
    subtotal REAL NOT NULL,
    discount REAL NOT NULL DEFAULT 0,
    cgst_total REAL NOT NULL,
    sgst_total REAL NOT NULL,
    igst_total REAL NOT NULL DEFAULT 0,
    grand_total REAL NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
  );

  CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    product_id INTEGER,
    product_name TEXT NOT NULL,
    product_code TEXT NOT NULL,
    hsn_code TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity REAL NOT NULL,
    price_ex_gst REAL NOT NULL,
    gst_rate REAL NOT NULL,
    cgst_amount REAL NOT NULL,
    sgst_amount REAL NOT NULL,
    igst_amount REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id),
    FOREIGN KEY(product_id) REFERENCES products(id)
  );

  CREATE TABLE IF NOT EXISTS inventory_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    type TEXT NOT NULL, -- 'restock', 'sale', 'adjustment', 'damage', 'return'
    quantity REAL NOT NULL,
    reason TEXT,
    date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(product_id) REFERENCES products(id)
  );

  CREATE TABLE IF NOT EXISTS alipay_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    out_trade_no TEXT UNIQUE NOT NULL,
    trade_no TEXT,
    subject TEXT NOT NULL,
    total_amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'WAIT_BUYER_PAY',
    qr_code TEXT NOT NULL,
    barcode_value TEXT NOT NULL,
    buyer_logon_id TEXT,
    notify_payload TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    paid_at DATETIME,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id)
  );
`);

try { db.exec("ALTER TABLE customers ADD COLUMN state TEXT"); } catch (e) {}
try { db.exec("ALTER TABLE invoices ADD COLUMN igst_total REAL NOT NULL DEFAULT 0"); } catch (e) {}
try { db.exec("ALTER TABLE invoice_items ADD COLUMN igst_amount REAL NOT NULL DEFAULT 0"); } catch (e) {}
try { db.exec("ALTER TABLE products ADD COLUMN stock REAL NOT NULL DEFAULT 0"); } catch (e) {}
try { db.exec("ALTER TABLE invoices ADD COLUMN status TEXT DEFAULT 'active'"); } catch (e) {}
try { db.exec("ALTER TABLE invoices ADD COLUMN payment_status TEXT DEFAULT 'Paid'"); } catch (e) {}
try { db.exec("ALTER TABLE invoices ADD COLUMN amount_paid REAL DEFAULT 0"); } catch (e) {}
try { db.exec("ALTER TABLE alipay_payments ADD COLUMN barcode_value TEXT NOT NULL DEFAULT ''"); } catch (e) {}

// Performance Indexes
db.exec('CREATE INDEX IF NOT EXISTS idx_invoices_date_status ON invoices(date, status)');
db.exec('CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice_id ON invoice_items(invoice_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_invoices_customer_id ON invoices(customer_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_products_stock ON products(stock)');
db.exec('CREATE INDEX IF NOT EXISTS idx_inventory_transactions_product_id ON inventory_transactions(product_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_alipay_payments_invoice_id ON alipay_payments(invoice_id)');
db.exec('CREATE INDEX IF NOT EXISTS idx_alipay_payments_status ON alipay_payments(status)');

// ⚡ Bolt: Indexes to optimize /api/customers queries with scalar subqueries
db.exec('CREATE INDEX IF NOT EXISTS idx_invoices_customer_id_status ON invoices(customer_id, status)');
db.exec('CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name)');

// ⚡ Bolt: Indexes to optimize /api/dashboard/analytics and /api/invoices queries
// idx_invoices_status_date prevents 'USE TEMP B-TREE' when grouping by date on active invoices
db.exec('CREATE INDEX IF NOT EXISTS idx_invoices_status_date ON invoices(status, date)');
// ⚡ Bolt: idx_invoices_status_day prevents 'USE TEMP B-TREE' when grouping by day in dashboard analytics
db.exec('CREATE INDEX IF NOT EXISTS idx_invoices_status_day ON invoices(status, substr(date, 1, 10))');
// idx_invoices_date_id optimizes the default sort order for the invoices list
db.exec('CREATE INDEX IF NOT EXISTS idx_invoices_date_id ON invoices(date DESC, id DESC)');

// ⚡ Bolt: Indexes to optimize /api/dashboard/analytics Top Products subquery
db.exec('CREATE INDEX IF NOT EXISTS idx_invoice_items_product_id_invoice_id ON invoice_items(product_id, invoice_id)');

// ⚡ Bolt: Indexes to optimize /api/products sorting and filtering
db.exec('CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)');
db.exec('CREATE INDEX IF NOT EXISTS idx_products_price_ex_gst ON products(price_ex_gst)');
db.exec('CREATE INDEX IF NOT EXISTS idx_products_stock ON products(stock)');
db.exec('CREATE INDEX IF NOT EXISTS idx_products_category_name ON products(category, name)');
db.exec('CREATE INDEX IF NOT EXISTS idx_products_category_price ON products(category, price_ex_gst)');
// ⚡ Bolt: Avoid TEMP B-TREE when sorting products by stock within a specific category
db.exec('CREATE INDEX IF NOT EXISTS idx_products_category_stock ON products(category, stock)');

db.exec(`
  CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_name TEXT NOT NULL,
    address TEXT NOT NULL,
    phone TEXT NOT NULL,
    gstin TEXT NOT NULL,
    state_code TEXT NOT NULL,
    logo_url TEXT,
    low_stock_threshold INTEGER DEFAULT 10
  );
`);

const settingsCount = db.prepare('SELECT count(*) as c FROM settings').get() as { c: number };
if (settingsCount.c === 0) {
  db.prepare('INSERT INTO settings (store_name, address, phone, gstin, state_code, low_stock_threshold) VALUES (?, ?, ?, ?, ?, ?)').run(
    'Bill Express',
    '123 Market Road, District, West Bengal - 700001',
    '9876543210',
    '19AAAAA0000A1Z5',
    '19 (West Bengal)',
    10
  );
}

try { db.exec("ALTER TABLE settings ADD COLUMN low_stock_threshold INTEGER DEFAULT 10"); } catch (e) {}

// Seed some default products if empty
const sampleProducts = [
  { code: 'UR46', name: 'Urea 46%', category: 'Fertilizer', unit: 'Bag', price: 250.00, gst: 5, hsn: '31021000' },
  { code: 'MONO36', name: 'Monocrotophos 36% SL', category: 'Pesticide', unit: 'Litre', price: 450.00, gst: 18, hsn: '38089199' },
  { code: 'DAP1846', name: 'DAP 18:46:0', category: 'Fertilizer', unit: 'Bag', price: 1200.00, gst: 5, hsn: '31053000' },
  { code: 'GLY41', name: 'Glyphosate 41% SL', category: 'Herbicide', unit: 'Litre', price: 380.00, gst: 18, hsn: '38089390' },
  { code: 'NPK102626', name: 'NPK 10:26:26', category: 'Fertilizer', unit: 'Bag', price: 1450.00, gst: 5, hsn: '31052000' },
  { code: 'IMIDA17', name: 'Imidacloprid 17.8% SL', category: 'Pesticide', unit: 'Litre', price: 850.00, gst: 18, hsn: '38089119' },
  { code: 'MOP60', name: 'Muriate of Potash 60%', category: 'Fertilizer', unit: 'Bag', price: 950.00, gst: 5, hsn: '31042000' },
  { code: 'SSP16', name: 'Single Super Phosphate 16%', category: 'Fertilizer', unit: 'Bag', price: 420.00, gst: 5, hsn: '31031100' },
  { code: 'CHLOR20', name: 'Chlorpyrifos 20% EC', category: 'Pesticide', unit: 'Litre', price: 320.00, gst: 18, hsn: '38089199' },
  { code: 'MANC75', name: 'Mancozeb 75% WP', category: 'Fungicide', unit: 'Kg', price: 480.00, gst: 18, hsn: '38089290' },
  { code: 'ZINC33', name: 'Zinc Sulphate 33%', category: 'Micronutrient', unit: 'Kg', price: 650.00, gst: 12, hsn: '28332990' },
  { code: 'HYBPAD', name: 'Hybrid Paddy Seeds', category: 'Seeds', unit: 'Kg', price: 350.00, gst: 0, hsn: '10061010' },
  { code: 'TOMF1', name: 'Tomato Seeds (F1)', category: 'Seeds', unit: 'Pkt', price: 120.00, gst: 0, hsn: '12099140' },
  { code: 'NEEM10K', name: 'Neem Oil 10000 ppm', category: 'Bio-Pesticide', unit: 'Litre', price: 550.00, gst: 5, hsn: '15159020' },
  { code: 'SUL80', name: 'Sulphur 80% WDG', category: 'Fungicide', unit: 'Kg', price: 180.00, gst: 18, hsn: '38089290' },
  { code: 'CORA18', name: 'Coragen 18.5% SC', category: 'Pesticide', unit: 'ml', price: 1850.00, gst: 18, hsn: '38089199' }
];

const insertMany = db.transaction((products: { code: string; name: string; category: string; unit: string; price: number; gst: number; hsn: string; }[]) => {
  if (products.length === 0) return;

  // ⚡ Bolt: Prepared a single static SQL statement for bulk insertion.
  // In better-sqlite3, preparing a single statement and executing it in a loop
  // inside a transaction is faster than dynamically building a massive batch string.
  const stmt = db.prepare(`INSERT OR IGNORE INTO products (code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock) VALUES (?, ?, ?, ?, ?, ?, ?, 100)`);
  for (const p of products) {
    stmt.run(p.code, p.name, p.category, p.unit, p.price, p.gst, p.hsn);
  }
});

insertMany(sampleProducts);

const sampleCustomers = [
  {
    name: 'Walk-in Customer',
    mobile: '13800000000',
    address: 'Front counter checkout',
    gstin: null,
    state: 'West Bengal'
  },
  {
    name: 'Demo Retail Buyer',
    mobile: '13900000000',
    address: 'No. 18 Market Road',
    gstin: '19AAAAA0000A1Z5',
    state: 'West Bengal'
  }
];

const insertCustomerIfMissing = db.prepare(`
  INSERT INTO customers (name, mobile, address, gstin, state)
  SELECT ?, ?, ?, ?, ?
  WHERE NOT EXISTS (SELECT 1 FROM customers WHERE mobile = ?)
`);

for (const customer of sampleCustomers) {
  insertCustomerIfMissing.run(
    customer.name,
    customer.mobile,
    customer.address,
    customer.gstin,
    customer.state,
    customer.mobile
  );
}

export default db;
