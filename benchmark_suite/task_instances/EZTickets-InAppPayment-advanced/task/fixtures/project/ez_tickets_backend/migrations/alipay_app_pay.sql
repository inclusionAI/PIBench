ALTER TABLE payments
  MODIFY payment_method enum('cash','card','cod','alipay') COLLATE utf8_unicode_ci NOT NULL;

CREATE TABLE IF NOT EXISTS alipay_orders (
  id int UNSIGNED NOT NULL AUTO_INCREMENT,
  out_trade_no varchar(64) NOT NULL,
  trade_no varchar(64) DEFAULT NULL,
  order_string text NOT NULL,
  amount int NOT NULL,
  alipay_amount decimal(11,2) NOT NULL,
  trade_status varchar(32) NOT NULL,
  user_id int UNSIGNED NOT NULL,
  show_id int UNSIGNED NOT NULL,
  booking_ids text NOT NULL,
  payment_id int UNSIGNED DEFAULT NULL,
  raw_status_payload text DEFAULT NULL,
  created_at datetime NOT NULL,
  updated_at datetime NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_alipay_orders_out_trade_no (out_trade_no),
  KEY idx_alipay_orders_trade_status (trade_status),
  KEY idx_alipay_orders_payment_id (payment_id)
);
