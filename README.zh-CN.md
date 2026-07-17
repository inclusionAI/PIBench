<div align="center">
  <h1>Alipay-PIBench：面向 Coding Agent 的真实支付集成 Benchmark</h1>
</div>

<div align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://arxiv.org/abs/2607.14573"><img src="https://img.shields.io/badge/Technical%20Report-arXiv-b31b1b.svg" alt="Technical Report: arXiv"></a>
</div>

<p align="center">
  <a href="README.md">English README</a>
</p>

---

## 🎯 项目介绍

Alipay-PIBench 是由支付宝提出的仓库级 Benchmark，用于评测 AI Coding Agent 完成真实支付集成任务的能力。它围绕支付宝开放平台产品和面向业务的项目仓库构建，包含 9 个支付产品项目和 18 个 Task Instance，覆盖 Basic（完成功能性支付集成）与 Advanced（具备风险意识的支付安全强化）两类 Scenario，评测功能正确性、可靠性、安全性和业务状态一致性。

- **支付 Benchmark 构建。** 每个支付产品对应一个代表性项目；每个任务由目标产品、业务流程、初始仓库和 Scenario 特定的集成需求共同构成。
- **基于 Rubric 的评测。** 每个 Scenario 通过 Rubric 定义确定性检查和 LLM 辅助标准，为结构、可执行性及支付领域要求生成与 Rubric 对齐的证据。
- **成对 Skill 实验。** 每个 Agent 会在相同任务、项目、Instruction 和环境下分别以使用及不使用 [`alipay-payment-integration`](https://github.com/alipay/ai/tree/main/skills/alipay-payment-integration) 的方式运行，从而支持按产品、Scenario、Agent 和 Skill 条件进行比较。

[![Alipay-PIBench 框架总览](assets/overview.png)](assets/overview.pdf)

## 🏆 主要结果

### 模型能力

[![不同支付宝支付产品和 Scenario 下的模型表现](assets/main-results.png)](assets/main-results.pdf)

模型能力解释了相当一部分性能差异，并且不同支付产品与 Scenario 的表现并不相同。在 with-skill 条件下，各模型的总体平均 Rubric Pass Rate（RPR）介于 **68.58% 和 91.37%** 之间。Basic 与 Advanced 任务分别反映 Agent 构建支付流程和保持支付安全行为的能力，两者相互补充。

其余研究问题的结果与详细分析请参阅[论文](https://arxiv.org/abs/2607.14573)。

## 🚀 快速开始

### 运行环境

建议在 Linux 主机或云服务器上运行，并提前准备：

- Bash
- Python 3
- Git
- Docker Engine，且当前用户有权访问 Docker daemon
- 能够访问所选模型服务、Docker 镜像源和任务所需的软件源
- 足够的磁盘空间用于构建任务镜像和保存运行产物

默认配置会启用 Docker，因为每个 Task Instance 都通过自己的 Dockerfile 定义应用、数据库和开发环境。

### 运行评测

本发行包完全自包含，包含 Benchmark Suite、确定性评测、LLM 辅助评测、三种 Agent Adapter（Claude Code、OpenClaw 和 Hermes）、PaySkills Runtime 源码、Docker 编排、并发执行能力和顶层 `run.sh`。用户不需要安装 PaySkills 平台。

```bash
# 查看命令说明。
./run.sh --help

# 创建 config/.env；已有文件不会被覆盖。
./run.sh --init

# 配置评测和本地密钥。
vim config/config.yaml
vim config/.env

# 检查包结构、配置、凭据、工具和 Docker。
./run.sh --doctor

# 列出选中的任务，不调用 Agent 或 Judge。
./run.sh --dry-run

# 开始评测。
./run.sh
```

`config/.env` 会被自动加载并被 Git 忽略。不要把真实 API Key 或支付宝沙箱私钥直接写入 `config/config.yaml`。

如需保留多份本地配置，可以显式传入配置文件，或设置 `PAYSKILLS_CONFIG`：

```bash
./run.sh --config config/config.local.yaml --doctor
./run.sh --config config/config.local.yaml
PAYSKILLS_CONFIG=/absolute/path/to/config.yaml ./run.sh --doctor
```

## ⚙️ 配置说明

当前配置文件是 `config/config.yaml`，`config/config.example.yaml` 是参考模板。

### 运行配置

```yaml
run:
  parallelism: 4
  output_dir: runs
  timeout_sec: 3600
  task_instances: []
```

- `parallelism`：同时执行的 Task Instance 上限
- `output_dir`：安全的相对产物目录；不能使用 `benchmark_suite/`、`config/`、`src/` 等发行包目录
- `timeout_sec`：分别应用于 `task/run.sh` 和 `evaluation/evaluate.sh` 的超时时间
- `task_instances`：可选的 Task Instance ID 列表；空列表表示选择全部 18 个任务

配置类型必须保持正确：`parallelism` 和 `timeout_sec` 使用正整数，`task_instances` 使用 YAML 列表，`env` 和 `runtime_inputs` 使用映射，`docker.enabled` 和 `docker.build` 使用布尔值。

### Agent 配置

```yaml
agent:
  type: claude-code
  mode: no-skill
  model: "your-agent-model"
  base_url: "https://your-provider.example/api/anthropic"
  api_key_env: AGENT_API_KEY
```

- `type`：`claude-code`、`openclaw` 或 `hermes`
- `mode`：`no-skill` 或 `with-skill`
- `model`：所选 Adapter 和供应商支持的模型名
- `base_url`：模型供应商地址，需要与 `api_key_env` 一起配置
- `api_key_env`：保存密钥的环境变量名称，不是密钥本身

在 `config/.env` 中填写对应变量：

```bash
AGENT_API_KEY="your-secret-key"
```

### LLM Judge 配置

```yaml
judge:
  base_url: "https://your-provider.example/v1"
  api_key_env: JUDGE_API_KEY
  model: "your-judge-model"
```

三个 Judge 字段应同时配置。对应密钥保存在 `config/.env`：

```bash
JUDGE_API_KEY="your-secret-key"
```

Agent 和 Judge 使用同一供应商凭据时，可以让两个 `api_key_env` 指向同一个环境变量。

### 额外环境变量

`env` 下的值会复制到每个 Task Instance 进程：

```yaml
env:
  CUSTOM_FLAG: value
```

特定 Task Instance 请求的结构化文件或密钥应通过 `runtime_inputs` 提供，而不是放入 `env`。

### 支付宝沙箱运行时输入

部分 Task Instance 需要支付宝沙箱信息。请从[支付宝开放平台沙箱](https://open.alipay.com/develop/sandbox/app)获取，并将其保存在 Benchmark Suite 和 Git 历史之外。

对于校验收款方身份的任务，`app_id` 与 `seller_id` 是两个不同值：app ID 标识沙箱应用，seller ID 是实际收款商户的 PID。不要把 app ID 原样填入 seller ID。

如需从 `config/.env` 提供沙箱信息：

```yaml
runtime_inputs:
  alipay_sandbox:
    schema: alipay.sandbox.v1
    source: env
    app_id_env: ALIPAY_APP_ID
    seller_id_env: ALIPAY_SELLER_ID
    gateway_env: ALIPAY_GATEWAY
    merchant_private_key_pkcs8_env: ALIPAY_MERCHANT_PRIVATE_KEY_PKCS8
    merchant_private_key_pkcs1_env: ALIPAY_MERCHANT_PRIVATE_KEY_PKCS1
    alipay_public_key_env: ALIPAY_PUBLIC_KEY
    sandbox_buyer_account_env: ALIPAY_SANDBOX_BUYER_ACCOUNT
    sandbox_buyer_login_password_env: ALIPAY_SANDBOX_BUYER_LOGIN_PASSWORD
    sandbox_buyer_pay_password_env: ALIPAY_SANDBOX_BUYER_PAY_PASSWORD
    miniapp_app_id_env: ALIPAY_MINIAPP_APP_ID
    op_app_id_env: ALIPAY_OP_APP_ID
```

然后在 `config/.env` 中补全所选任务需要的变量。本套件同时包含 Java 和非 Java 项目，完整运行时应同时提供 PKCS#8 和 PKCS#1 两种商户私钥格式。

也可以使用本地 JSON 文件：

```yaml
runtime_inputs:
  alipay_sandbox:
    schema: alipay.sandbox.v1
    source: file
    path: ../secrets/alipay-sandbox-keys.json
```

相对路径以所选配置文件所在目录为基准解析。使用 `config/config.yaml` 时，上例实际指向发行包根目录下的 `secrets/alipay-sandbox-keys.json`。不要把该本地文件提交到 Git。

JSON 结构如下：

```json
{
  "app_id": "<your-sandbox-app-id>",
  "seller_id": "<your-sandbox-merchant-pid>",
  "gateway": "https://openapi-sandbox.dl.alipaydev.com/gateway.do",
  "sign_type": "RSA2",
  "merchant_private_key_pkcs8": "<merchant-private-key-pkcs8>",
  "merchant_private_key_pkcs1": "<merchant-private-key-pkcs1>",
  "alipay_public_key": "<alipay-public-key>",
  "sandbox_buyer": {
    "account": "<sandbox-buyer-account>",
    "login_password": "<sandbox-buyer-login-password>",
    "pay_password": "<sandbox-buyer-pay-password>"
  },
  "miniapp_app_id": "<optional-miniapp-app-id>",
  "op_app_id": "<optional-op-app-id>"
}
```

请补全所选任务需要的字段。在 Docker 模式下，Runtime 会将输入以只读方式挂载到 `/run/payskills/inputs/`，并通过 Task Instance 声明的环境变量暴露，例如 `ALIPAY_SANDBOX_KEYS_FILE`。如果任务声明了 `workspace_path`，Runtime 还会在 Agent 启动前将文件复制到 `/workspace`。

### Docker 配置

```yaml
docker:
  enabled: true
  build: true
  image: ""
  network: ""
```

- `enabled`：在 Docker 内运行 Task Instance；发行包默认值为 `true`
- `build`：构建每个选中任务的 `task/Dockerfile`
- `image`：`build` 为 `false` 时使用的本地已有镜像
- `network`：可选的 Docker 网络名

Docker 模式会在沙箱中挂载 `/task_instance`、`/workspace`、`/output` 和 `/opt/payskills_runtime`。Task 镜像必须包含 `bash`、`python3` 和 `git`。

### 指定任务运行

在 `config/config.yaml` 中填写 Task Instance ID：

```yaml
run:
  task_instances:
    - EDoc-MobileWebPayment-basic
    - Litemall-PCWebPayment-advanced
```

运行 `./run.sh --dry-run` 可以确认最终任务列表和所需 Helper。

## 📦 运行结果

每次评测都会创建：

```text
runs/<timestamp>/
  summary.json
  <task-instance-label>/
    result.json
    execution.json
    logs/
      run_stdout.log
      diff_export.log
      evaluation_output.txt
    artifacts/
      agent_trace.json
      agent_events.jsonl
      agent_evidence.json
      patch.diff
      changed_files.txt
      code_files/
```

- `summary.json`：本次运行的任务索引和汇总状态
- `result.json`：Evaluation 写入的总分及逐条 Rubric 通过状态和分数
- `execution.json`：run、diff 和 evaluation 阶段的 Runtime 状态
- `logs/`：各阶段原始日志
- `agent_trace.json`：标准化的 Agent 轮次调用链
- `agent_events.jsonl`：详细的 Agent 内部事件流
- `agent_evidence.json`：提供给 LLM 辅助评测的紧凑证据
- `patch.diff`、`changed_files.txt`、`code_files/`：Agent 对 Workspace 产生的修改

运行产物可能包含完整的 Agent 输入、输出、命令和运行时沙箱材料。应将整个运行目录视为敏感数据，未经检查不要公开上传。

## 🧩 契约说明

### Task Instance 契约

每个 Task Instance 遵循以下结构：

```text
benchmark_suite/task_instances/<task-instance-id>/
  task_instance.toml
  task/
    Dockerfile
    instruction.md
    turns.json
    run.sh
    fixtures/
    skills/
  evaluation/
    evaluate.sh
    rubrics.json
    deterministic/
    llm_assisted/
```

`task/run.sh` 调用所选 Agent 并写入非评分产物。`evaluation/evaluate.sh` 执行确定性评测和 LLM 辅助评测，并写入 `$OUTPUT_DIR/result.json`。

`result.json` 是评分契约，包含数值类型的 `score`、`max_score`、摘要和 `rubrics` 列表。每条 Rubric 记录自己的通过状态、得分、满分、类型和诊断信息。

Task Instance 调用 `payskills-agent drive-turns` 后，Agent Helper 会在 `artifacts/` 下写入 `agent_trace.json`、`agent_evidence.json` 和 `agent_events.jsonl`。`agent_evidence.json` 用于 LLM 辅助评测，`agent_trace.json` 用于轮次级摘要，`agent_events.jsonl` 用于详细排障。

发行包会拒绝 `environment/Dockerfile`、Task 根目录 `run.sh`、Task 根目录 `test.sh` 等旧版结构。

### 发行包契约

`manifest.json` 是机器可读的发行包契约，记录：

- 顶层 Runner 命令
- Task Instance 必需路径
- 配置和 Helper CLI 契约
- 标准运行产物路径

`./run.sh --doctor` 会在创建运行目录前校验 manifest、包结构、所选任务、配置、必需命令、凭据、运行时输入和 Docker 状态。

## 🛠️ 常见问题

### Docker daemon 不可访问

请启动 Docker，并确认当前用户执行 `docker info` 能成功。

### 缺少 Agent 或 Judge 模型/API Key

按照 `./run.sh --doctor` 输出的 `ERROR` 和 `HINT` 检查 `agent`、`judge` 以及 `config/.env` 中被引用的变量。

### 缺少支付宝沙箱输入

请配置 `runtime_inputs.alipay_sandbox`，并补全所选任务需要的环境变量或本地 JSON 文件。

### 只检查配置，不开始评测

```bash
./run.sh --doctor
./run.sh --dry-run
```

## ©️ 版权

- 作者：Alipay Team，DATA X AI Team
