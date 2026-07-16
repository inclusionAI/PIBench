# SaaS Starter merchant-withholding rubric applicability

| Layer | Rubric | Decision | Reason | Evidence |
|---|---|---|---|---|
| L1 | dep_sdk | 测 | 需要支付宝 SDK 或 RSA2 签名/验签能力 | static.dep_sdk |
| L1 | dep_build | 测 | 项目必须能构建并启动 | integ.dep_build |
| L2 | logic_impl | 测 | 签约和扣款不能是空实现 | integration happy path + LLM |
| L2 | logic_api | 测 | 商家扣款 mock gateway 方法必须正确 | integ.method_app_pay / method_trade_pay / success_accept |
| L2 | integ_pay | 测 | 签约、协议号、扣款成功状态要可观察 | integ.sign_notify_accept / pay_notify_success / success_accept |
| L2 | notify_endpoint | 测 | 签约和支付通知入口必须存在并处理有效通知 | integration notification checks |
| L2 | refund_impl | 不测 | 当前订阅 case 不要求退款 | n/a |
| L3 | integ_notify_reject | 测 | 无签名、坏签名、错字段不得推进状态 | unsigned/bad_signature/wrong_* |
| L3 | notify_verify_fields | 测 | 金额、协议、用户/team、订单号绑定是商家扣款核心 | wrong_amount/wrong_agreement/wrong_user |
| L3 | integ_notify_accept | 测 | 正确通知必须推进状态，防止误杀正确实现 | success_accept |
| L3 | pay_result_rule | 测 | 不能把同步受理当最终成功 | pending_not_final / async_acceptance_not_final |
| L3 | secret_storage | 测 | 真实密钥不得入库 | static.secret_storage |
| L3 | secret_gitignore | 测 | 敏感材料应被排除 | static.secret_gitignore |
| L3 | unique_id_check | 测 | 重复通知不得重复履约 | duplicate_notify_idempotent |
| L3 | query_compensation | 测 | pending/unknown 需要查询或保持非终态 | query_methods_available / pending_not_final |
| L4 | exception_api_strategy | 测 | 网关错误不能放行 | gateway_error_fail_closed |
| L4 | payment_pending_polling | 测 | 处理中不得开通最终权益 | pending_not_final |
| L4 | no_repeat_pay_before_confirm | 测 | 上一笔未确认前不得重复扣款 | no_repeat_pay_before_confirm |
| L4 | request_idempotency_keys | 测 | 请求号要和业务单据绑定 | request_idempotency_keys |
| L4 | amount_accounting_rule | 测 | 金额不能混淆或越限 | wrong_amount_reject / deduct_limit |
| L4 | state_machine_terminal | 测 | 旧通知不得覆盖终态 | terminal_not_overwritten |
| L5 | withholding_agreement_query | 测 | 协议查询能力需要存在 | query_methods_available |
| L5 | withholding_deduct_limit | 测 | 单笔/周期金额限制要受控 | deduct_limit |
| L5 | withholding_async_acceptance | 测 | 扣款受理不等于成功 | async_acceptance_not_final |
| L5 | withholding_retry_bound | 部分测 | 不测具体次数，测未确认前不得无限重复扣款 | no_repeat_pay_before_confirm + LLM |
| L5 | withholding_unsign_stop | LLM 补充 | 当前最小产品无固定解约入口，不做硬 API 断言 | llm.L5_retry_unsign_limits |
| L6 | status UX | 测轻量项 | 只检查 pricing/status 稳定入口，不依赖文案/DOM 细节 | e2e.* |
