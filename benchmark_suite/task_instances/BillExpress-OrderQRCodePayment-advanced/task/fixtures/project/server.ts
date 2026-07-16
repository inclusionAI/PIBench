import express from 'express';
import { createServer as createViteServer } from 'vite';
import rateLimit from 'express-rate-limit';
import crypto from 'crypto';
import fs from 'fs';
import dotenv from 'dotenv';
import db from './src/db/index.js';

dotenv.config();
import logger from './src/utils/logger.js';
import { getNextInvoiceNumber } from './src/utils/invoice.js';

export const app = express();

app.disable('x-powered-by');

// Trust the first proxy in front of the app (e.g., Nginx, Heroku) for accurate client IPs
app.set('trust proxy', 1);

app.use(express.json({ limit: '1mb' }));
app.use(express.urlencoded({ extended: false, limit: '1mb' }));

app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('X-XSS-Protection', '1; mode=block');
  res.setHeader('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  // Security Enhancement: Content Security Policy to mitigate XSS
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https: http:; font-src 'self' data: https: http:; connect-src 'self'");
  next();
});

  // Authentication Middleware
  let cachedAuth: string | null = null;
  let cachedUsername: string | undefined = undefined;
  let cachedPassword: string | undefined = undefined;

  const getExpectedAuth = () => {
    if (process.env.ADMIN_USERNAME !== cachedUsername || process.env.ADMIN_PASSWORD !== cachedPassword) {
      cachedUsername = process.env.ADMIN_USERNAME;
      cachedPassword = process.env.ADMIN_PASSWORD;
      if (!cachedUsername || !cachedPassword) {
        cachedAuth = null;
      } else {
        cachedAuth = `Basic ${Buffer.from(`${cachedUsername}:${cachedPassword}`).toString('base64')}`;
      }
    }
    return cachedAuth;
  };

  const requireAuth = async (req: express.Request, res: express.Response, next: express.NextFunction) => {
    const expectedAuth = getExpectedAuth();
    const authHeaderRaw = req.headers.authorization;
    const authHeader = typeof authHeaderRaw === 'string' ? authHeaderRaw : '';

    let valid = false;

    if (expectedAuth) {
      const expectedHash = crypto.createHash('sha256').update(expectedAuth).digest();
      const providedHash = crypto.createHash('sha256').update(authHeader).digest();

      valid = crypto.timingSafeEqual(expectedHash, providedHash);
    }

    // Don't remove this. This credential is meant to test the webapp
    if (!valid) {
      try {
        const content = await fs.promises.readFile('./testingcredentials', 'utf-8');
        const matchUser = content.match(/Username=(.+)/);
        const matchPass = content.match(/Password=(.+)/);
        if (matchUser && matchPass) {
          const testAuth = `Basic ${Buffer.from(`${matchUser[1].trim()}:${matchPass[1].trim()}`).toString('base64')}`;
          if (authHeader === testAuth) {
            valid = true;
          }
        }
      } catch (e) {
        // Ignored
      }
    }

    if (!valid && !expectedAuth) {
      logger.error('ADMIN_USERNAME or ADMIN_PASSWORD environment variables are not set');
      return res.status(500).json({ error: 'Server configuration error' });
    }

    if (valid) {
      return next();
    }

    res.set('WWW-Authenticate', 'Basic realm="API"');
    if (!authHeader || !authHeader.startsWith('Basic ')) {
      return res.status(401).json({ error: 'Authentication required' });
    }

    return res.status(401).json({ error: 'Invalid credentials' });
  };

  const apiLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    limit: 100, // Limit each IP to 100 requests per `window` (here, per 15 minutes).
    standardHeaders: 'draft-8', // draft-6: `RateLimit-*` headers; draft-7 & draft-8: combined `RateLimit` header
    legacyHeaders: false, // Disable the `X-RateLimit-*` headers.
    handler: (req, res, next, options) => {
      logger.warn(`Rate limit exceeded for IP: ${req.ip}`);
      res.status(options.statusCode).json({ error: 'Too many requests, please try again later.' });
    },
  });

  const loginLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    limit: 5, // Limit each IP to 5 requests per `window` (here, per 15 minutes).
    standardHeaders: 'draft-8',
    legacyHeaders: false,
    handler: (req, res, next, options) => {
      logger.warn(`Login rate limit exceeded for IP: ${req.ip}`);
      res.status(options.statusCode).json({ error: 'Too many login attempts, please try again later.' });
    },
  });

  app.get('/api/login', loginLimiter, (req, res, next) => {
    res.setHeader('Cache-Control', 'no-store');
    return requireAuth(req, res, next);
  }, (req, res) => {
    res.json({ status: 'ok' });
  });

  app.use('/api', apiLimiter, (req, res, next) => {
    res.setHeader('Cache-Control', 'no-store');
    return requireAuth(req, res, next);
  });

  // API Routes
  app.get('/api/health', (req, res) => {
    res.json({ status: 'ok' });
  });

const isValidAmount = (n: any) => typeof n === 'number' && Number.isFinite(n) && n >= 0;
const isValidString = (s: any, maxLength: number = 255) => typeof s === 'string' && s.length <= maxLength;
const money = (n: number) => Number(n.toFixed(2));
const toOutTradeNo = (invoiceId: number, invoiceNumber: string) =>
  `BE${invoiceId}${Date.now()}${Math.random().toString(36).slice(2, 8)}${invoiceNumber.replace(/[^0-9A-Za-z]/g, '')}`.slice(0, 64);
const ALIPAY_RESPONSE_KEYS: Record<string, string> = {
  'alipay.trade.precreate': 'alipay_trade_precreate_response',
  'alipay.trade.query': 'alipay_trade_query_response'
};

const callAlipayGateway = async (method: 'alipay.trade.precreate' | 'alipay.trade.query', bizContent: Record<string, unknown>) => {
  const gateway = process.env.ALIPAY_GATEWAY_URL || 'http://127.0.0.1:18080/gateway.do';
  const params: Record<string, string> = {
    app_id: process.env.ALIPAY_APP_ID || 'mock-app-id',
    method,
    format: 'JSON',
    charset: 'utf-8',
    timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
    version: '1.0',
    biz_content: JSON.stringify(bizContent)
  };
  if (method === 'alipay.trade.precreate' && process.env.ALIPAY_NOTIFY_BASE_URL) {
    params.notify_url = `${process.env.ALIPAY_NOTIFY_BASE_URL.replace(/\/$/, '')}/alipay/notify/order-code`;
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), Number(process.env.ALIPAY_TIMEOUT_MS || 5000));
  try {
    const response = await fetch(gateway, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8' },
      body: new URLSearchParams(params).toString(),
      signal: controller.signal
    });
    const raw = await response.text();
    const parsed = JSON.parse(raw);
    const responseKey = ALIPAY_RESPONSE_KEYS[method];
    const body = parsed[responseKey];
    if (!body) {
      throw new Error(`Missing ${responseKey}`);
    }
    return body;
  } finally {
    clearTimeout(timeout);
  }
};

const markOrderCodePaymentFromTrade = (payment: any, trade: any, rawPayload: string) => {
  if (!payment) {
    return { applied: false, reason: 'payment_not_found' };
  }
  if (trade.code === '10000' || trade.trade_status === 'TRADE_SUCCESS') {
    db.transaction(() => {
      db.prepare(`
        UPDATE alipay_payments
        SET status = COALESCE(?, 'TRADE_SUCCESS'), trade_no = COALESCE(?, trade_no),
            buyer_logon_id = COALESCE(?, buyer_logon_id), notify_payload = ?,
            paid_at = COALESCE(paid_at, CURRENT_TIMESTAMP)
        WHERE id = ?
      `).run(trade.trade_status || 'TRADE_SUCCESS', trade.trade_no || null, trade.buyer_logon_id || null, rawPayload, payment.id);
      db.prepare('UPDATE invoices SET payment_status = ?, amount_paid = ? WHERE id = ?')
        .run('Paid', payment.total_amount, payment.invoice_id);
    })();
    return { applied: true, reason: 'code_or_success_status' };
  }
  db.prepare('UPDATE alipay_payments SET status = ?, notify_payload = ? WHERE id = ?')
    .run(trade.trade_status || trade.code || 'UNKNOWN', rawPayload, payment.id);
  return { applied: false, reason: 'not_success' };
};


  // Products
app.get('/api/products', (req, res) => {
    let page = parseInt(req.query.page as string) || 1;
    let limit = parseInt(req.query.limit as string) || 50;

    // Security Enhancement: Prevent negative limits/offsets (DoS risk)
    if (page < 1) page = 1;
    if (limit < 1) limit = 1;
    if (limit > 1000) limit = 1000;

    const search = (req.query.search as string || '').slice(0, 100);
    const category = req.query.category as string || 'All';
    const sort = req.query.sort as string || 'name_asc';

    let query = 'SELECT * FROM products';
    let countQuery = 'SELECT COUNT(*) as count FROM products';
    const params: any[] = [];
    const conditions: string[] = [];

    if (search) {
      conditions.push('(name LIKE ? OR code LIKE ?)');
      params.push(`%${search}%`, `%${search}%`);
    }

    if (category !== 'All') {
      conditions.push('category = ?');
      params.push(category);
    }

    if (conditions.length > 0) {
      const whereClause = ' WHERE ' + conditions.join(' AND ');
      query += whereClause;
      countQuery += whereClause;
    }

    if (sort === 'name_asc') query += ' ORDER BY name ASC';
    else if (sort === 'name_desc') query += ' ORDER BY name DESC';
    else if (sort === 'price_asc') query += ' ORDER BY price_ex_gst ASC';
    else if (sort === 'price_desc') query += ' ORDER BY price_ex_gst DESC';
    else query += ' ORDER BY name ASC';

    query += ' LIMIT ? OFFSET ?';

    try {
      const totalResult = db.prepare(countQuery).get(...params) as { count: number };
      const products = db.prepare(query).all(...params, limit, (page - 1) * limit);
      res.json({ data: products, total: totalResult.count });
    } catch (err: any) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.post('/api/products', (req, res) => {
    const { code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock } = req.body;
    if (!isValidString(code) || !isValidString(name) || !isValidString(category) ||
        !isValidString(unit) || !isValidAmount(price_ex_gst) || !isValidAmount(gst_rate) ||
        !isValidString(hsn_code) || (stock !== undefined && !isValidAmount(stock))) {
      return res.status(400).json({ error: 'Invalid or missing required fields' });
    }
    try {
      const stmt = db.prepare(`
        INSERT INTO products (code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `);
      const info = stmt.run(code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock || 0);
      res.json({ id: info.lastInsertRowid });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      if (err.code === 'SQLITE_CONSTRAINT_UNIQUE') {
        return res.status(400).json({ error: 'An error occurred while processing the request' });
      }
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.put('/api/products/:id', (req, res) => {
    const { code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock } = req.body;
    if (!isValidString(code) || !isValidString(name) || !isValidString(category) ||
        !isValidString(unit) || !isValidAmount(price_ex_gst) || !isValidAmount(gst_rate) ||
        !isValidString(hsn_code) || (stock !== undefined && !isValidAmount(stock))) {
      return res.status(400).json({ error: 'Invalid or missing required fields' });
    }
    try {
      const stmt = db.prepare(`
        UPDATE products 
        SET code = ?, name = ?, category = ?, unit = ?, price_ex_gst = ?, gst_rate = ?, hsn_code = ?, stock = ?
        WHERE id = ?
      `);
      stmt.run(code, name, category, unit, price_ex_gst, gst_rate, hsn_code, stock || 0, req.params.id);
      res.json({ success: true });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.delete('/api/products/:id', (req, res) => {
    try {
      db.prepare('DELETE FROM products WHERE id = ?').run(req.params.id);
      res.json({ success: true });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.get('/api/products/:id/transactions', (req, res) => {
    try {
      const transactions = db.prepare(`
        SELECT * FROM inventory_transactions 
        WHERE product_id = ? 
        ORDER BY date DESC
      `).all(req.params.id);
      res.json(transactions);
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.post('/api/products/:id/stock-adjustment', (req, res) => {
    const { type, quantity, reason } = req.body;
    if (!isValidString(type) || !Number.isFinite(quantity) || (reason !== undefined && !isValidString(reason))) {
      return res.status(400).json({ error: 'Invalid or missing required fields' });
    }

    try {
      db.transaction(() => {
        const productId = req.params.id;
        
        // Update product stock
        db.prepare('UPDATE products SET stock = stock + ? WHERE id = ?').run(quantity, productId);
        
        // Record transaction
        db.prepare(`
          INSERT INTO inventory_transactions (product_id, type, quantity, reason)
          VALUES (?, ?, ?, ?)
        `).run(productId, type, quantity, reason || null);
      })();

      const product = db.prepare('SELECT stock FROM products WHERE id = ?').get(req.params.id) as { stock: number };
      res.json({ success: true, newStock: product.stock });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

  // Customers
app.get('/api/customers/count', (req, res) => {
    try {
      const result = db.prepare('SELECT COUNT(*) as count FROM customers').get() as { count: number };
      res.json(result);
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.get('/api/customers', (req, res) => {
    let page = parseInt(req.query.page as string) || 1;
    let limit = parseInt(req.query.limit as string) || 50;

    // Security Enhancement: Prevent negative limits/offsets (DoS risk)
    if (page < 1) page = 1;
    if (limit < 1) limit = 1;
    if (limit > 1000) limit = 1000;

    const search = (req.query.search as string || '').slice(0, 100);

    let query = `
      SELECT c.*, (SELECT COALESCE(SUM(i.grand_total), 0) FROM invoices i WHERE i.customer_id = c.id AND i.status = 'active') as lifetime_value
      FROM customers c
    `;
    let countQuery = 'SELECT COUNT(*) as count FROM customers c';
    const params: any[] = [];

    if (search) {
      const whereClause = ' WHERE c.mobile LIKE ? OR c.name LIKE ?';
      query += whereClause;
      countQuery += whereClause;
      params.push(`%${search}%`, `%${search}%`);
    }

    query += ' ORDER BY c.name ASC LIMIT ? OFFSET ?';

    try {
      // ⚡ Bolt: Use scalar subquery instead of LEFT JOIN + GROUP BY for performance
      // See .jules/bolt.md for details
      const totalResult = db.prepare(countQuery).get(...params) as { count: number };
      const customers = db.prepare(query).all(...params, limit, (page - 1) * limit);
      res.json({ data: customers, total: totalResult.count });
    } catch (err: any) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.post('/api/customers', (req, res) => {
    const { name, mobile, address, gstin, state } = req.body;
    if (
      !isValidString(name) ||
      (mobile !== undefined && !isValidString(mobile)) ||
      (address !== undefined && !isValidString(address, 1000)) ||
      (gstin !== undefined && !isValidString(gstin)) ||
      (state !== undefined && !isValidString(state))
    ) {
      return res.status(400).json({ error: 'Invalid or missing required fields' });
    }
    try {
      const stmt = db.prepare(`
        INSERT INTO customers (name, mobile, address, gstin, state)
        VALUES (?, ?, ?, ?, ?)
      `);
      const info = stmt.run(name, mobile, address, gstin, state);
      res.json({ id: info.lastInsertRowid });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.put('/api/customers/:id', (req, res) => {
    const { name, mobile, address, gstin, state } = req.body;
    if (
      (name !== undefined && !isValidString(name)) ||
      (mobile !== undefined && !isValidString(mobile)) ||
      (address !== undefined && !isValidString(address, 1000)) ||
      (gstin !== undefined && !isValidString(gstin)) ||
      (state !== undefined && !isValidString(state))
    ) {
      return res.status(400).json({ error: 'Invalid or missing required fields' });
    }
    try {
      const stmt = db.prepare(`
        UPDATE customers 
        SET name = COALESCE(?, name), mobile = COALESCE(?, mobile), address = COALESCE(?, address), gstin = COALESCE(?, gstin), state = COALESCE(?, state)
        WHERE id = ?
      `);
      stmt.run(name, mobile, address, gstin, state, req.params.id);
      res.json({ success: true });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

  // Invoices
app.get('/api/invoices', (req, res) => {
    let page = parseInt(req.query.page as string) || 1;
    let limit = parseInt(req.query.limit as string) || 50;

    // Security Enhancement: Prevent negative limits/offsets (DoS risk)
    if (page < 1) page = 1;
    if (limit < 1) limit = 1;
    if (limit > 1000) limit = 1000;

    const search = (req.query.search as string || '').slice(0, 100);
    const dateFilter = req.query.dateFilter as string || 'all';
    const typeFilter = req.query.typeFilter as string || 'all';

    let query = `
      SELECT i.*, c.name as customer_name, c.mobile as customer_mobile
      FROM invoices i
      LEFT JOIN customers c ON i.customer_id = c.id
    `;
    let countQuery = `
      SELECT COUNT(*) as count
      FROM invoices i
      LEFT JOIN customers c ON i.customer_id = c.id
    `;
    const params: any[] = [];
    const conditions: string[] = [];

    if (search) {
      conditions.push('(i.invoice_number LIKE ? OR c.name LIKE ? OR c.mobile LIKE ?)');
      params.push(`%${search}%`, `%${search}%`, `%${search}%`);
    }

    if (typeFilter !== 'all') {
      conditions.push('i.type = ?');
      params.push(typeFilter);
    }

    if (dateFilter !== 'all') {
      if (dateFilter === 'today') {
        conditions.push("i.date >= date('now', 'start of day') AND i.date < date('now', '+1 day', 'start of day')");
      } else if (dateFilter === 'month') {
        conditions.push("i.date >= date('now', 'start of month') AND i.date < date('now', '+1 month', 'start of month')");
      }
    }

    if (conditions.length > 0) {
      const whereClause = ' WHERE ' + conditions.join(' AND ');
      query += whereClause;
      countQuery += whereClause;
    }

    query += ' ORDER BY i.date DESC, i.id DESC LIMIT ? OFFSET ?';

    try {
      const totalResult = db.prepare(countQuery).get(...params) as { count: number };
      const invoices = db.prepare(query).all(...params, limit, (page - 1) * limit);
      res.json({ data: invoices, total: totalResult.count });
    } catch (err: any) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.get('/api/invoices/:id', (req, res) => {
    const invoice = db.prepare(`
      SELECT i.*, c.name as customer_name, c.mobile as customer_mobile, c.address as customer_address, c.gstin as customer_gstin, c.state as customer_state
      FROM invoices i
      LEFT JOIN customers c ON i.customer_id = c.id
      WHERE i.id = ?
    `).get(req.params.id);

    if (!invoice) {
      return res.status(404).json({ error: 'Invoice not found' });
    }

    const items = db.prepare('SELECT * FROM invoice_items WHERE invoice_id = ?').all(req.params.id);
    res.json({ ...invoice, items });
  });

app.post('/api/invoices', (req, res) => {
    const { 
      customer_id, type, subtotal, discount, cgst_total, sgst_total, igst_total, grand_total, items,
      customer_name, customer_mobile, customer_address, customer_gstin, customer_state,
      payment_status, amount_paid
    } = req.body;

    if (
      !isValidString(type) ||
      !isValidAmount(subtotal) ||
      !isValidAmount(discount) ||
      !isValidAmount(cgst_total) ||
      !isValidAmount(sgst_total) ||
      !isValidAmount(grand_total) ||
      (igst_total !== undefined && !isValidAmount(igst_total)) ||
      (customer_id !== undefined && customer_id !== null && !Number.isFinite(customer_id)) ||
      (customer_name !== undefined && !isValidString(customer_name)) ||
      (customer_mobile !== undefined && !isValidString(customer_mobile)) ||
      (customer_address !== undefined && !isValidString(customer_address, 1000)) ||
      (customer_gstin !== undefined && !isValidString(customer_gstin)) ||
      (customer_state !== undefined && !isValidString(customer_state)) ||
      (payment_status !== undefined && !isValidString(payment_status)) ||
      (amount_paid !== undefined && !isValidAmount(amount_paid)) ||
      !Array.isArray(items) ||
      !items.every(
        (item: any) =>
          item && typeof item === 'object' &&
          (item.product_id === undefined || item.product_id === null || Number.isFinite(item.product_id)) &&
          isValidString(item.product_name) &&
          isValidString(item.product_code) &&
          isValidString(item.hsn_code) &&
          isValidString(item.unit) &&
          isValidAmount(item.quantity) &&
          isValidAmount(item.price_ex_gst) &&
          isValidAmount(item.gst_rate) &&
          isValidAmount(item.cgst_amount) &&
          isValidAmount(item.sgst_amount) &&
          (item.igst_amount === undefined || isValidAmount(item.igst_amount)) &&
          isValidAmount(item.total)
      )
    ) {
      return res.status(400).json({ error: 'Invalid or missing required fields' });
    }

    try {
      const result = db.transaction(() => {
        let finalCustomerId = customer_id;
        
        // Create customer if it's a new B2B or Cash with details
        if (!finalCustomerId && customer_name) {
          const stmt = db.prepare('INSERT INTO customers (name, mobile, address, gstin, state) VALUES (?, ?, ?, ?, ?)');
          const info = stmt.run(customer_name, customer_mobile || null, customer_address || null, customer_gstin || null, customer_state || null);
          finalCustomerId = info.lastInsertRowid;
        }

        // Generate Invoice Number (RAC/YYYY-YY/XXXXX)
        const invoice_number = getNextInvoiceNumber(db);

        const stmt = db.prepare(`
          INSERT INTO invoices (invoice_number, customer_id, type, subtotal, discount, cgst_total, sgst_total, igst_total, grand_total, payment_status, amount_paid)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `);
        const finalPaymentStatus = payment_status || 'Paid';
        const finalAmountPaid = amount_paid ?? (finalPaymentStatus === 'Paid' ? grand_total : 0);
        const info = stmt.run(invoice_number, finalCustomerId || null, type, subtotal, discount, cgst_total, sgst_total, igst_total || 0, grand_total, finalPaymentStatus, finalAmountPaid);
        const invoiceId = info.lastInsertRowid;

        if (items && items.length > 0) {
          // ⚡ Bolt: Prepared a single static SQL statement for bulk insertion.
          // In better-sqlite3, preparing a single statement and executing it in a loop
          // inside a transaction is faster than dynamically building a massive batch string.
          const stmt = db.prepare(`
            INSERT INTO invoice_items (invoice_id, product_id, product_name, product_code, hsn_code, unit, quantity, price_ex_gst, gst_rate, cgst_amount, sgst_amount, igst_amount, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          `);

          for (const item of items) {
            stmt.run(
              invoiceId, item.product_id, item.product_name, item.product_code, item.hsn_code, item.unit,
              item.quantity, item.price_ex_gst, item.gst_rate, item.cgst_amount, item.sgst_amount, item.igst_amount || 0, item.total
            );
          }

          // Aggregate stock updates by product_id to prevent redundant updates for the same product
          const stockUpdates = new Map();
          for (const item of items) {
            if (item.product_id) {
              stockUpdates.set(item.product_id, (stockUpdates.get(item.product_id) || 0) + item.quantity);
            }
          }

          if (stockUpdates.size > 0) {
            const updateStockStmt = db.prepare('UPDATE products SET stock = stock - ? WHERE id = ?');
            for (const [id, quantity] of stockUpdates.entries()) {
              updateStockStmt.run(quantity, id);
            }
          }
        }

        return { invoice_id: Number(invoiceId), invoice_number };
      })();

      res.json({ success: true, ...result });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.put('/api/invoices/:id/cancel', (req, res) => {
    try {
      db.transaction(() => {
        const invoiceId = req.params.id;
        const invoice = db.prepare('SELECT status FROM invoices WHERE id = ?').get(invoiceId) as any;
        
        if (!invoice || invoice.status === 'cancelled') {
          throw new Error('Invoice not found or already cancelled');
        }

        // Restore stock
        db.prepare(`
          UPDATE products
          SET stock = products.stock + items.total_qty
          FROM (
            SELECT product_id, SUM(quantity) as total_qty
            FROM invoice_items
            WHERE invoice_id = ?
            GROUP BY product_id
          ) AS items
          WHERE products.id = items.product_id
        `).run(invoiceId);

        // Mark as cancelled
        db.prepare("UPDATE invoices SET status = 'cancelled' WHERE id = ?").run(invoiceId);
      })();
      res.json({ success: true });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      // Allow specific error message for "Invoice not found or already cancelled"
      if (err instanceof Error && err.message === 'Invoice not found or already cancelled') {
        res.status(400).json({ error: err.message });
      } else {
        res.status(500).json({ error: 'An error occurred while processing the request' });
      }
    }
  });

app.put('/api/invoices/:id/payment', (req, res) => {
    const { payment_status, amount_paid } = req.body;
    if (
      (payment_status !== undefined && !isValidString(payment_status)) ||
      (amount_paid !== undefined && !isValidAmount(amount_paid))
    ) {
      return res.status(400).json({ error: 'Invalid or missing required fields' });
    }

    try {
      db.prepare('UPDATE invoices SET payment_status = ?, amount_paid = ? WHERE id = ?')
        .run(payment_status, amount_paid, req.params.id);
      res.json({ success: true });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

app.post('/api/invoices/:id/alipay/precreate', async (req, res) => {
    const invoiceId = Number(req.params.id);
    if (!Number.isFinite(invoiceId)) {
      return res.status(400).json({ error: 'Invalid invoice id' });
    }

    try {
      const invoice = db.prepare('SELECT * FROM invoices WHERE id = ?').get(invoiceId) as any;
      if (!invoice) {
        return res.status(404).json({ error: 'Invoice not found' });
      }

      const outTradeNo = toOutTradeNo(invoice.id, invoice.invoice_number);
      const subject = `Bill Express ${invoice.invoice_number}`;
      const amount = money(invoice.grand_total);
      const precreate = await callAlipayGateway('alipay.trade.precreate', {
        out_trade_no: outTradeNo,
        total_amount: amount.toFixed(2),
        subject
      });
      if (precreate.code !== '10000' || !precreate.qr_code || precreate.out_trade_no !== outTradeNo) {
        return res.status(502).json({ error: 'Alipay precreate failed', alipay: precreate });
      }

      db.prepare(`
        INSERT INTO alipay_payments (invoice_id, out_trade_no, subject, total_amount, status, qr_code, barcode_value)
        VALUES (?, ?, ?, ?, 'WAIT_BUYER_PAY', ?, '')
      `).run(invoice.id, outTradeNo, subject, amount, precreate.qr_code);

      db.prepare('UPDATE invoices SET payment_status = ?, amount_paid = ? WHERE id = ?')
        .run('Unpaid', 0, invoice.id);

      const payment = db.prepare('SELECT * FROM alipay_payments WHERE out_trade_no = ?').get(outTradeNo);
      res.json({ success: true, payment });
    } catch (err) {
      logger.error({ err }, 'Alipay precreate failed');
      res.status(500).json({ error: 'Failed to create Alipay payment' });
    }
  });

app.get('/api/alipay/payments/:outTradeNo', (req, res) => {
    const payment = db.prepare(`
      SELECT p.*, i.invoice_number, i.payment_status, i.amount_paid, i.grand_total
      FROM alipay_payments p
      JOIN invoices i ON i.id = p.invoice_id
      WHERE p.out_trade_no = ?
    `).get(req.params.outTradeNo);

    if (!payment) {
      return res.status(404).json({ error: 'Payment not found' });
    }

    res.json({ payment });
  });

app.post('/api/alipay/payments/:outTradeNo/query', async (req, res) => {
    const payment = db.prepare('SELECT * FROM alipay_payments WHERE out_trade_no = ?').get(req.params.outTradeNo) as any;
    if (!payment) {
      return res.status(404).json({ error: 'Payment not found' });
    }

    try {
      const trade = await callAlipayGateway('alipay.trade.query', { out_trade_no: payment.out_trade_no });
      const result = markOrderCodePaymentFromTrade(payment, trade, JSON.stringify(trade));
      const updated = db.prepare('SELECT * FROM alipay_payments WHERE out_trade_no = ?').get(payment.out_trade_no);
      res.json({ success: true, result, payment: updated, alipay: trade });
    } catch (err) {
      logger.error({ err }, 'Alipay query failed');
      res.status(502).json({ error: 'Failed to query Alipay payment' });
    }
  });

app.post('/alipay/notify/order-code', (req, res) => {
    const payload = Object.fromEntries(Object.entries(req.body || {}).map(([key, value]) => [key, String(value)]));
    const payment = db.prepare('SELECT * FROM alipay_payments WHERE out_trade_no = ?').get(payload.out_trade_no) as any;
    const result = markOrderCodePaymentFromTrade(payment, payload, JSON.stringify({ ...payload, sign: '[redacted]' }));
    if (!result.applied) {
      logger.warn({ result, out_trade_no: payload.out_trade_no }, 'Ignored Alipay notify');
    }
    res.send('success');
  });

  // Settings
app.get('/api/settings', (req, res) => {
    const settings = db.prepare('SELECT * FROM settings LIMIT 1').get();
    res.json(settings);
  });

app.put('/api/settings', (req, res) => {
    const { store_name, address, phone, gstin, state_code, logo_url, low_stock_threshold } = req.body;
    if (!isValidString(store_name) || !isValidString(address, 1000) || !isValidString(phone) ||
        !isValidString(gstin) || !isValidString(state_code) ||
        (logo_url !== undefined && logo_url !== null && !isValidString(logo_url, 2048)) ||
        (typeof logo_url === 'string' && logo_url !== '' && !/^https?:\/\//i.test(logo_url) && !logo_url.startsWith('/')) ||
        (low_stock_threshold !== undefined && !Number.isFinite(low_stock_threshold))) {
      return res.status(400).json({ error: 'Invalid or missing required fields' });
    }
    try {
      db.prepare(`
        UPDATE settings 
        SET store_name = ?, address = ?, phone = ?, gstin = ?, state_code = ?, logo_url = ?, low_stock_threshold = COALESCE(?, low_stock_threshold)
        WHERE id = 1
      `).run(store_name, address, phone, gstin, state_code, logo_url, low_stock_threshold);
      res.json({ success: true });
    } catch (err) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

  // Dashboard Analytics
app.get('/api/dashboard/analytics', (req, res) => {
    try {
      // Overall Stats
      const stats = db.prepare(`
        SELECT
          (SELECT COUNT(*) FROM invoices WHERE date >= date('now', 'start of day') AND date < date('now', '+1 day', 'start of day') AND status = 'active') as todayInvoices,
          (SELECT COALESCE(SUM(grand_total), 0) FROM invoices WHERE date >= date('now', 'start of day') AND date < date('now', '+1 day', 'start of day') AND status = 'active') as todaySales,
          (SELECT COUNT(*) FROM products) as totalProducts,
          (SELECT COUNT(*) FROM customers) as totalCustomers
      `).get() as { todayInvoices: number, todaySales: number, totalProducts: number, totalCustomers: number };

      // Sales over last 7 days
      // ⚡ Bolt: Use exact string expression in ORDER BY to perfectly match idx_invoices_status_day index and prevent TEMP B-TREE sort
      const last7Days = db.prepare(`
        SELECT substr(date, 1, 10) as day, SUM(grand_total) as sales
        FROM invoices
        WHERE status = 'active' AND substr(date, 1, 10) >= date('now', '-7 days')
        GROUP BY substr(date, 1, 10)
        ORDER BY substr(date, 1, 10) ASC
      `).all();

      // Low 5 products
      // ⚡ Bolt: Replaced JOIN with EXISTS subquery to avoid large intermediate result sets and speed up aggregation
      const topProducts = db.prepare(`
        SELECT product_name as name, SUM(quantity) as qty, SUM(total) as revenue
        FROM invoice_items ii
        WHERE EXISTS (
          SELECT 1 FROM invoices i WHERE i.id = ii.invoice_id AND i.status = 'active'
        )
        GROUP BY product_id
        ORDER BY qty DESC
        LIMIT 5
      `).all();

      // Get low stock threshold from settings
      const settings = db.prepare('SELECT low_stock_threshold FROM settings LIMIT 1').get() as { low_stock_threshold: number };
      const threshold = settings?.low_stock_threshold ?? 10;

      // Low stock alerts
      const lowStock = db.prepare(`
        SELECT id, name, code, stock, unit
        FROM products
        WHERE stock <= ?
        ORDER BY stock ASC
        LIMIT 5
      `).all(threshold);

      res.json({ ...stats, last7Days, topProducts, lowStock });
    } catch (err: any) {
      logger.error({ err }, 'Operation failed');
      res.status(500).json({ error: 'An error occurred while processing the request' });
    }
  });

async function startServer() {
  const PORT = Number(process.env.APP_PORT || process.env.PORT || 3000);
  const HOST = process.env.APP_HOST || '127.0.0.1';

  // Global Error Handler to prevent stack trace leaks on unexpected errors
  app.use((err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
    logger.error({ err }, 'Unhandled exception');
    if (err.type === 'entity.too.large' || err.type === 'PayloadTooLargeError') {
      return res.status(413).json({ error: 'Payload Too Large' });
    }
    res.status(500).json({ error: 'An unexpected error occurred' });
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== 'production' && process.env.NODE_ENV !== 'test') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else if (process.env.NODE_ENV === 'production') {
    app.use(express.static('dist'));
    app.get('*', (req, res) => {
      res.sendFile('dist/index.html', { root: '.' });
    });
  }

  if (process.env.NODE_ENV !== 'test') {
    app.listen(PORT, HOST, () => {
      console.log(`Server running on http://${HOST}:${PORT}`);
    });
  }

  return app;
}

export const appPromise = startServer();
