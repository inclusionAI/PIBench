# Bill Express 收银台 支付宝支付安全加固

## 背景

Bill Express 已经有一个最小的支付宝订单码支付 POC，但它还不足以承载真实门店收银。你的任务是在保留 POS 商品、客户、库存和 invoice 流程的基础上，把商家生成二维码、顾客扫码付款、系统确认收款这一链路加固到可用于评测的业务实现。

## 接口与配置约定

评测侧会启动 Python 版支付宝 mock 网关，并通过配置文件或环境变量注入网关地址、appId 和密钥材料。请使用支付宝官方 SDK 或符合 OpenAPI 规范的客户端接入这个外部网关，不要在业务应用内增加自造的支付成功捷径、演示结果选择器、自行生成空密钥配置或硬编码真实密钥。

## 任务目标

应用应通过 `alipay.trade.precreate` 为当前 invoice 创建订单码，并用 `alipay.trade.query` 或验签后的异步通知确认最终支付结果。`out_trade_no` 必须绑定 invoice，金额必须绑定 invoice 应付金额；二维码展示、页面跳转、同步受理、等待支付、超时或未知状态都不能直接当作成功。通知或查询结果需要先验签，再校验应用/商户身份、订单号、支付宝交易号、金额和状态等关键业务字段。重复通知、重复查询和旧事件需要幂等处理，并保护 Paid 等终态不被回滚或覆盖。

请继续暴露评测可观察的业务入口：`POST /api/invoices/:id/alipay/precreate`、`GET /api/alipay/payments/:outTradeNo`、`POST /api/alipay/payments/:outTradeNo/query`，以及一个异步通知入口，例如 `/alipay/notify/order-code`。这些入口不要求固定内部实现，但需要真实驱动支付记录、invoice 状态和网关调用。

付款成功后还要支持退款业务。`POST /api/invoices/:id/alipay/refund` 用于对已支付 invoice 发起部分退款或全额退款，`POST /api/invoices/:id/alipay/refund/query` 用于确认退款结果。未支付 invoice 不能走退款；同一次退款重试应复用同一个 `out_request_no` 并保持幂等，不同部分退款应使用不同请求号。退款成功不能只看同步 `code=10000`，需要结合 `fund_change` 或权威退款查询；部分退款、全额退款、未支付关闭/取消和已支付退款的业务边界要清晰。

## 完成说明

完成后请概述你如何验证二维码预下单、通知/查询确认、幂等、异常状态和退款链路。

完成任务前，请停止并清理你在本次任务中启动的所有应用服务、后台进程和 Docker/Compose 容器，并确认相关监听端口已经释放。
