# DeepRepair Mission Control v1

第一版目标：先跑通两部分代码。

1. **电脑端前端**：`Open MCT + deck.gl Hero View` 的 Mission Control 控制台。当前版本暂不实现完整数字孪生，只保留 Twin 区域占位与 Real/Twin 的接口命名，为下一版接入 Twin Service 做准备。
2. **树莓派端飞船模拟器**：树莓派模拟远程深空探测器，提供遥测、故障注入、白名单命令执行、端侧 agents，并支持调用树莓派本地 Gemma 4（LiteRT-LM）做 onboard diagnosis。

> 开发联调可以用 `scripts/start_probe_mock.sh` 启用 `mock` Gemma 兜底，方便你在没有下载模型时先跑通前端和命令链路。真正上树莓派录 demo 时，使用真实 Gemma 启动脚本；此时如果本地 Gemma 没接上，agent 接口会直接报错，避免无意中录成 mock。

---

## 目录结构

```text
frontend/        # 电脑端 Mission Control 前端，React + TypeScript + deck.gl + Open MCT page
pi_probe/        # 树莓派端 Probe Emulator + onboard agents + Gemma adapter
scripts/         # 启动、安装、联调脚本
docs/            # 接口、agent 设计和演示说明
```

---

## 一、树莓派端启动

### 1. 安装 Python 依赖

```bash
cd deeprepair_mission_control_v1
bash scripts/pi_install.sh
```

### 2. 启动飞船模拟器（开发/mock 模式）

```bash
bash scripts/start_probe_mock.sh
```

默认端口：`8010`。

健康检查：

```bash
curl http://localhost:8010/health
```

### 3. 启动飞船模拟器（真实 Gemma 4 LiteRT 模式）

先准备默认 Gemma 4 E2B LiteRT-LM：

```bash
bash scripts/pi_prepare_gemma_e2b.sh
```

然后启动：

```bash
bash scripts/start_probe_gemma_e2b.sh
```

默认真实模型配置：

```bash
GEMMA_BACKEND=litert_cli
GEMMA_MODEL_REPO=litert-community/gemma-4-E2B-it-litert-lm
GEMMA_MODEL_FILE=gemma-4-E2B-it.litertlm
REQUIRE_REAL_GEMMA=1
```

验证 Gemma 是否真的接上：

```bash
curl http://localhost:8010/api/agent/gemma/status
curl -X POST http://localhost:8010/api/agent/diagnose \
  -H 'Content-Type: application/json' \
  -d '{"reason":"manual-test"}'
```

---

## 二、电脑端前端启动

### 1. 设置树莓派 API 地址

复制环境变量示例：

```bash
cd frontend
cp .env.example .env
```

如果树莓派 IP 是 `192.168.1.80`，修改：

```bash
VITE_PROBE_API_BASE=http://192.168.1.80:8010
VITE_PROBE_WS_BASE=ws://192.168.1.80:8010
```

本机联调 mock 时可用：

```bash
VITE_PROBE_API_BASE=http://localhost:8010
VITE_PROBE_WS_BASE=ws://localhost:8010
```

### 2. 安装并启动前端

```bash
npm install
npm run dev
```

打开：

```text
http://localhost:5173
```

Open MCT 独立页：

```text
http://localhost:5173/openmct.html
```

---

## 三、端到端联调顺序

1. 树莓派启动 `scripts/start_probe_mock.sh` 或 `scripts/start_probe_gemma_e2b.sh`
2. 电脑端启动 `frontend/npm run dev`
3. 前端顶部检查 `Probe Link: ONLINE`
4. 点击 `Inject Thermal Fault`
5. 点击 `Run Onboard Gemma Diagnosis`
6. 点击 `ENTER_SAFE_MODE` / `DISABLE_PAYLOAD` 等命令
7. 观察遥测状态变化与 agent 输出
8. 点击 `Open MCT` 查看 Open MCT telemetry page
9. deck.gl Hero 视图中点击/触发命令后会显示 uplink signal animation

---

## 四、当前版本包含什么 / 不包含什么

### 包含

- 电脑端 Mission Control UI
- deck.gl Hero Signal Delay View
- Open MCT 独立 telemetry page（通过 Pi API 获取历史/实时数据）
- 树莓派飞船模拟器
- 故障注入：thermal / comms / power / sensor
- 白名单命令执行
- onboard agent 设计与代码
- Gemma 4 LiteRT-LM 适配器（Python API / CLI / mock fallback）
- 调试脚本与 curl 示例

### 暂不包含

- 完整 Digital Twin Service
- Real vs Twin 预测曲线叠加
- 完整 HITL 审计回放
- 真实 Open MCT 高级对象树布局保存

下一版重点就是把 `twin/*` channel 与 `Run in Twin` 真实接入。

---

## 五、重要安全设计

- 所有命令必须在 `ALLOWED_COMMANDS` 白名单内。
- agent 不能执行 shell。
- `REQUIRE_REAL_GEMMA=1` 时，Gemma 未接通会拒绝诊断请求。
- 端侧 Gemma 只做摘要与建议，不直接自动执行高风险命令。
