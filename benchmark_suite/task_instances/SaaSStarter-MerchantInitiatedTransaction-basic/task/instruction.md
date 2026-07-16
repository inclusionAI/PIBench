# SaaS Starter：接入支付宝商家扣款订阅闭环

## 背景

你正在维护 SaaS Starter，一个面向团队套餐的订阅项目。本题真正考察的是在这个 SaaS Starter 项目中完成支付宝商家扣款风格的订阅基础闭环。

## 接口与配置约定

评测侧会启动 Python 版支付宝 mock 网关，并通过 `ALIPAY_GATEWAY` 或 `ALIPAY_GATEWAY_URL` 注入地址。商家扣款在本 benchmark 中不走真实沙箱全链路，请不要连接生产或真实沙箱网关，也不要在业务应用里加入直接改状态的测试捷径。真实私钥、token、app secret 和生产凭据都不能写入业务源码、数据库或日志。

## 任务目标

产品体验应保持自然：用户从 pricing 页面选择套餐，发起支付宝签约；签约成功后，系统保存协议身份；随后基于已保存协议发起周期扣款，并在扣款成功后让订阅状态可观察。签约请求使用 `alipay.trade.app.pay` 语义，后续扣款使用 `alipay.trade.pay` 语义；网关受理、pending 或同步返回不等于最终付款成功。

为了让评测稳定观察你的实现，请保留这些应用入口，内部组织方式不限：`POST /api/alipay/sign-contract` 发起签约并返回 `externalAgreementNo`、`outTradeNo` 等业务标识；`POST /api/alipay/sign-notify` 接收签约通知并持久化协议；`POST /api/alipay/withhold` 对已签约团队发起扣款；`POST /api/alipay/pay-notify` 接收扣款通知；`GET /api/alipay/status?teamId=1` 返回订阅、签约和最近一次扣款状态。

## 完成说明

完成后请简要说明你修改了哪些文件，以及如何验证 pricing 入口、签约、周期扣款和状态查询闭环。

完成任务前，请停止并清理你在本次任务中启动的所有应用服务、后台进程和 Docker/Compose 容器，并确认相关监听端口已经释放。
