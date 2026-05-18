# DeepRepair v1 API

Base URL 默认：`http://127.0.0.1:8010`

## Health

```bash
GET /health
```

## 当前遥测

```bash
GET /api/telemetry/current
```

## 历史遥测

```bash
GET /api/telemetry/history?metric=thermal.temp_c&limit=300
```

## WebSocket 实时遥测

```text
ws://127.0.0.1:8010/ws/telemetry
```

## 注入故障

```bash
POST /api/faults/inject
{
  "fault": "thermal"
}
```

可选：`thermal`, `comms`, `power`, `sensor`, `clear`

## 发送命令

```bash
POST /api/command
{
  "action": "ENTER_SAFE_MODE",
  "params": {},
  "source": "mission-control-ui"
}
```

## 运行端侧 E4B 诊断

```bash
POST /api/agent/diagnose
{
  "reason": "manual-ui"
}
```

## E4B 状态

```bash
GET /api/agent/gemma/status
```
