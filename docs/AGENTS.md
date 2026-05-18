# 飞船端 agents 设计

当前 v1 先把 Mac 本机 Probe backend 里的 agents 固定成 4 个小角色，避免一开始做成不可控的“万能 agent”。

## 1. TelemetryAnomalyAgent

职责：读取最近遥测窗口，基于阈值和趋势发现异常。

输出：

- severity
- affected_subsystems
- anomaly_summary
- recommended_agent_next_step

## 2. OnboardE4BDiagnosisAgent

职责：调用远程服务器 vLLM 上的 E4B backend，对当前故障做结构化摘要。

输出必须是 JSON：

```json
{
  "fault_summary": ["...", "..."],
  "likely_causes": [
    {"cause": "...", "confidence": 0.72, "evidence": ["..."]}
  ],
  "immediate_safe_actions": ["ENTER_SAFE_MODE", "DISABLE_PAYLOAD"],
  "uncertainty": "..."
}
```

## 3. SafetyGateAgent

职责：验证 E4B 建议动作是否来自白名单，过滤高风险动作。

## 4. CommandExecutorAgent

职责：只执行白名单命令，并更新 probe state。

> v1 不允许 agent 直接执行任意 shell 命令，不允许自由修改代码。
