# Bill Express 收银台 接入支付宝支付

## 背景

你正在维护 Bill Express，一个面向线下门店的收银台/POS 项目。请在不破坏商品、客户、库存、开票等既有功能的前提下，把 `Save & Generate Invoice` 后的收款流程接入支付宝订单码支付：商家为一张 invoice 生成二维码，顾客扫码后完成付款。

## 接口与配置约定

项目源码位于当前工作目录，启动入口保持为 `bash start.sh`。启动脚本应完成依赖安装、数据初始化和服务启动，并输出 `APP_READY=...` 供测试侧发现应用地址。

支付宝配置材料位于 `alipay-sandbox-keys.json`，测试环境也可能通过环境变量覆盖网关地址、appId 和密钥材料。请使用支付宝官方 SDK 或符合 OpenAPI 规范的客户端接入；不要自行生成空密钥配置，也不要把真实私钥、token、完整密钥写入业务源码、数据库或日志。

## 任务目标

业务上需要使用订单码/当面付主扫链路，核心调用是 `alipay.trade.precreate`，并通过异步通知验签或 `alipay.trade.query` 确认最终状态。二维码展示、页面跳转或同步返回都只能作为过程信息；invoice 只有在订单号、应付金额和支付状态匹配后才能进入已支付状态。

为了让评测稳定观察你的实现，请保留这些应用入口，内部组织方式不限：`POST /api/invoices/:id/alipay/precreate` 为指定 invoice 创建订单码支付单；`GET /api/alipay/payments/:outTradeNo` 返回支付单和 invoice 状态；`POST /api/alipay/payments/:outTradeNo/query` 刷新交易状态；同时提供可接收支付宝异步通知的入口。

## 完成说明

完成后请简要说明你修改了哪些文件，以及如何验证 invoice 生成二维码到支付状态更新这一闭环。

完成任务前，请停止并清理你在本次任务中启动的所有应用服务、后台进程和 Docker/Compose 容器，并确认相关监听端口已经释放。
