# Bill Express 收银台 接入支付宝支付

## 背景

你正在维护 Bill Express，一个面向线下门店的收银台/POS 项目。请在不影响商品、客户、库存、开票等既有能力的前提下，把 invoice 结账流程接入支付宝付款码支付：顾客出示付款码，收银员录入 `auth_code` 后完成收款，并能在支付结果不明确时查询确认。

## 接口与配置约定

项目源码位于当前工作目录，启动入口保持为 `bash start.sh`。启动脚本应完成依赖安装、数据初始化和服务启动，并输出 `APP_READY=...` 供测试侧发现应用地址。

支付宝配置材料位于 `alipay-sandbox-keys.json`，测试环境也可能通过环境变量覆盖网关地址、appId 和密钥材料。请使用支付宝官方 SDK 或符合 OpenAPI 规范的客户端接入；不要自行生成空密钥配置，也不要把真实私钥、token、完整密钥写入业务源码、数据库或日志。

## 任务目标

业务上需要使用当面付付款码链路，核心调用是 `alipay.trade.pay`，并为支付不确定状态提供 `alipay.trade.query` 或等价权威查询。请让 `out_trade_no` 与 invoice 绑定，支付金额等于 invoice 应付金额，只有权威结果确认成功且关键字段匹配时才把 invoice 标记为已支付。

为了让评测稳定观察你的实现，请保留这些应用入口，内部组织方式不限：`POST /api/invoices/:id/alipay/barcode/pay` 接收 `{ "auth_code": "..." }` 并发起付款码收款；`GET /api/invoices/:id/alipay/barcode/payment` 返回最近一次支付记录和 invoice 状态；`POST /api/invoices/:id/alipay/barcode/query` 刷新交易状态。

## 完成说明

完成后请简要说明你修改了哪些文件，以及如何验证收银员输入付款码到 invoice 支付状态更新这一闭环。

完成任务前，请停止并清理你在本次任务中启动的所有应用服务、后台进程和 Docker/Compose 容器，并确认相关监听端口已经释放。
