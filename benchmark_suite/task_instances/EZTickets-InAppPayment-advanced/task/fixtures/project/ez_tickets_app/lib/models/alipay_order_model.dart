import '../helper/typedefs.dart';

class AlipayOrderModel {
  final String outTradeNo;
  final String orderStr;
  final String tradeStatus;

  const AlipayOrderModel({
    required this.outTradeNo,
    required this.orderStr,
    required this.tradeStatus,
  });

  factory AlipayOrderModel.fromJson(JSON json) {
    return AlipayOrderModel(
      outTradeNo: (json['out_trade_no'] ?? json['outTradeNo']) as String,
      orderStr: (json['order_str'] ?? json['orderStr']) as String,
      tradeStatus: (json['trade_status'] ?? json['tradeStatus']) as String,
    );
  }
}
