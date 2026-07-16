import '../helper/typedefs.dart';

class AlipayOrderStatusModel {
  final String outTradeNo;
  final String tradeStatus;
  final int? paymentId;

  const AlipayOrderStatusModel({
    required this.outTradeNo,
    required this.tradeStatus,
    this.paymentId,
  });

  bool get isPaid => tradeStatus == 'TRADE_SUCCESS' || tradeStatus == 'TRADE_FINISHED';
  bool get isClosed => tradeStatus == 'TRADE_CLOSED';
  bool get isPending => tradeStatus == 'WAIT_BUYER_PAY' || tradeStatus == 'ORDER_STRING_CREATED';

  factory AlipayOrderStatusModel.fromJson(JSON json) {
    return AlipayOrderStatusModel(
      outTradeNo: (json['out_trade_no'] ?? json['outTradeNo']) as String,
      tradeStatus: (json['trade_status'] ?? json['tradeStatus']) as String,
      paymentId: (json['payment_id'] ?? json['paymentId']) as int?,
    );
  }
}
