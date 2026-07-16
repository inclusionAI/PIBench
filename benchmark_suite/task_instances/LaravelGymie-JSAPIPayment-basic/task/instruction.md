# Gymie 会员卡购买 接入支付宝支付

## 背景

你面前是一个名为 **Gymie** 的健身房会员系统（Laravel 12 + SQLite），代码在 `/workspace`。用户可以在支付宝小程序中浏览会员卡套餐，填写会员信息并创建待支付订单。当前系统已经具备会员卡商品、订单记录、小程序页面和本地后端 API，但付款流程仍停留在"创建订单"阶段：用户无法在支付宝小程序中完成付款，付款确认后也不会自动开通会员。

## 任务目标

请在现有会员卡购买流程上补齐 **支付宝小程序内付款能力**。目标是：用户提交会员卡订单后可以在支付宝小程序内完成支付；服务端拿到可信支付结果后，再更新订单并完成会员、订阅、账单等业务履约。

## 业务目标

- 保留现有会员卡套餐、订单创建和订单查询流程，不要新增一套绕过原流程的替代 API。
- 支付交易必须由服务端通过支付宝开放平台或题目提供的沙箱网关创建；不要用本地伪造的交易号、固定字符串或客户端自报状态代替支付平台结果。
- 创建小程序支付交易时，请使用运行环境中提供的可用沙箱买家标识，并保持标识类型与支付宝接口字段语义一致。
- 小程序端应使用后端返回的支付交易信息唤起支付宝原生收银台；前端支付回调只能用于刷新状态，不能单独决定订单已支付或会员已开通。
- 服务端需要接收并校验支付结果，只有可信结果才能推进订单状态和会员履约；无效、篡改或不可信的通知不能推进订单。
- 会员开通、订阅、账单或支付流水等履约逻辑应与支付成功状态一致，并能避免重复通知造成重复履约。
- 支付配置、密钥、证书和网关地址必须来自环境变量或配置文件，不要把私钥、证书或 token 内容硬编码进源码。

## 接口与配置约定

| 方法 | 路径 | 请求要求 | 期望行为 |
| --- | --- | --- | --- |
| `GET` | `/api/membership-checkout/plans` | 无需登录 | 返回 200 和可购买会员卡列表。 |
| `POST` | `/api/membership-checkout/orders` | JSON 包含 `plan_id`、`buyer_name`、`buyer_contact`、`buyer_email`；可选 `buyer_id`、`buyer_open_id`、`buyer_logon_id`、`buyer_auth_code` | 创建待支付会员卡订单；返回 JSON 中包含 `order.checkout_no`、`order.status`、`order.amount`、`order.tradeNO`。 |
| `GET` | `/api/membership-checkout/orders/{checkout_no}` | 使用创建订单返回的 `checkout_no` | 返回订单当前支付状态、金额和会员卡信息。 |
| `POST` | `/membership-checkout/notify` | 支付宝异步通知表单 | 验证通知后推进订单状态；无效通知不得推进。 |

注意：返回给小程序的交易字段名必须是 `tradeNO`（大小写敏感），小程序端也要用这个字段唤起支付。

## 运行环境

- 应用目录：`/workspace`，PHP 8.4 / composer / node 已安装，依赖已装好（`vendor/`、`node_modules/` 就绪，vite 已构建）。
- 数据库：SQLite（`storage/app/database.sqlite`），已完成迁移和 seed。本地调试可用 `php artisan serve --host=127.0.0.1 --port=$APP_PORT`；实际端口以 `.env` 中的 `APP_URL` 为准。
- 如需新增 composer 依赖，容器内可联网执行 `composer require`。
- 容器内已写入支付宝沙箱配置到 `/workspace/.env`。其中 `ALIPAY_GATEWAY_URL` 指向本地记录代理，代理会把标准 OpenAPI form 请求转发到真实支付宝沙箱，并记录请求参数供集成测试核验；不要改成 mock 交易创建或本地伪造 tradeNO。为了自动化验证支付成功后的服务端处理，异步成功通知会由测试环境使用本地 mock 支付宝签名生成。

```
ALIPAY_GATEWAY_URL=http://127.0.0.1:8233/gateway.do  # 转发到真实支付宝沙箱的本地代理
ALIPAY_APP_ID=<真实沙箱商户应用 appid>
ALIPAY_MINIAPP_APP_ID=<支付宝小程序 appid，JSAPI 交易放入 op_app_id>
ALIPAY_APP_PRIVATE_KEY_PATH=/output/real-alipay-keys/app_private_key.pem
ALIPAY_ALIPAY_PUBLIC_KEY_PATH=/output/real-alipay-keys/alipay_public_key.pem  # 测试环境用于验响应/验回调的支付宝公钥
ALIPAY_NOTIFY_URL=<测试环境写入的当前服务回调地址>
ALIPAY_SANDBOX_BUYER_ID=<沙箱买家 id，如运行环境提供>
ALIPAY_SANDBOX_BUYER_LOGON_ID=<沙箱买家登录账号，如运行环境提供>
```

- 请按支付宝标准 OpenAPI + RSA2 签名流程创建交易、处理响应和验签通知。集成测试会检查请求是否真实发往沙箱代理、返回给小程序的 `tradeNO` 是否来自接口响应，以及 mock 签名的成功通知能否推进可信履约、重复通知是否幂等。

## 边界说明

- 不要求实现完整后台管理系统。
- 不要求实现退款、部分退款或营销资金处理。
- 不要求在容器内真实启动支付宝小程序开发者工具；小程序代码通过静态检查和模拟测试验证。
- 不要求真实生产密钥；使用上面提供的沙箱配置即可。

完成后请确保：`php artisan serve` 可启动、迁移可重放（`php artisan migrate:fresh --seed` 不报错）、固定接口约定全部可用。

完成任务前，请停止并清理你在本次任务中启动的所有应用服务、后台进程和 Docker/Compose 容器，并确认相关监听端口已经释放。
