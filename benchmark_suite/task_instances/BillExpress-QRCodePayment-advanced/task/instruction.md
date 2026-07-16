# Bill Express 收银台：支付宝支付能力安全加固

## 背景

Bill Express 已经有一个最小的支付宝付款码支付 POC，但它还不足以承载真实门店收银。你的任务是在保留 POS 商品、客户、库存和 invoice 流程的基础上，把这条付款码链路加固到可用于评测的业务实现。

## 接口与配置约定

评测侧会启动 Python 版支付宝 mock 网关，并通过配置文件或环境变量注入网关地址、appId 和密钥材料。请使用支付宝官方 SDK 或符合 OpenAPI 规范的客户端接入这个外部网关，不要在业务应用内增加自造的支付成功捷径、演示结果选择器、自行生成空密钥配置或硬编码真实密钥。

## 任务目标

收银员录入顾客付款码后，应用应通过 `alipay.trade.pay` 发起当面付付款码收款，并在 `WAIT_BUYER_PAY`、`10003`、超时、处理中或未知状态下使用 `alipay.trade.query` 做补偿确认。`out_trade_no` 必须绑定当前 invoice，金额必须绑定 invoice 应付金额；只有匹配的权威成功结果才能把 invoice 置为 Paid。重复提交、重复网关响应和旧事件不能造成重复扣款、重复入账或覆盖终态，完整 `auth_code` 也不应落库或出现在日志里。

请继续暴露评测可观察的业务入口：`POST /api/invoices/:id/alipay/barcode/pay`、`GET /api/invoices/:id/alipay/barcode/payment`、`POST /api/invoices/:id/alipay/barcode/query`。这些入口不要求固定内部实现，但需要真实驱动支付记录、invoice 状态和网关调用。

付款成功后还要支持退款业务。`POST /api/invoices/:id/alipay/refund` 用于对已支付 invoice 发起部分退款或全额退款，`POST /api/invoices/:id/alipay/refund/query` 用于确认退款结果。未支付 invoice 不能走退款；同一次退款重试应复用同一个 `out_request_no` 并保持幂等，不同部分退款应使用不同请求号。退款链路需要按支付宝的资金结果确认实际退资，避免只把接口调用成功当作退款成功；同时要区分未支付订单的撤销/关闭、已支付订单的退款，以及部分退款和全额退款后的本地状态。

## 完成说明

完成后请概述你如何验证付款、查询、幂等、异常状态和退款链路。

完成任务前，请停止并清理你在本次任务中启动的所有应用服务、后台进程和 Docker/Compose 容器，并确认相关监听端口已经释放。
