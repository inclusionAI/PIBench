import 'package:flutter_test/flutter_test.dart';

import 'package:ez_ticketz_app/models/alipay_order_model.dart';
import 'package:ez_ticketz_app/models/alipay_order_status_model.dart';

void main() {
  group('AlipayOrderModel', () {
    test('parses basic create response fields', () {
      final model = AlipayOrderModel.fromJson(<String, dynamic>{
        'out_trade_no': 'EZT123',
        'order_str': 'signed_order_string',
        'trade_status': 'WAIT_BUYER_PAY',
      });

      expect(model.outTradeNo, 'EZT123');
      expect(model.orderStr, 'signed_order_string');
      expect(model.tradeStatus, 'WAIT_BUYER_PAY');
    });
  });

  group('AlipayOrderStatusModel', () {
    test('parses confirm response fields and paid state', () {
      final model = AlipayOrderStatusModel.fromJson(<String, dynamic>{
        'out_trade_no': 'EZT123',
        'trade_status': 'TRADE_SUCCESS',
        'payment_id': 99,
      });

      expect(model.outTradeNo, 'EZT123');
      expect(model.tradeStatus, 'TRADE_SUCCESS');
      expect(model.paymentId, 99);
      expect(model.isPaid, isTrue);
    });
  });
}
