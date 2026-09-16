# P2 LangGraph / Intent Router / Tool Calling

P2 将 P1.5 的静态 RAG + Freshness Gate 升级为可执行的文旅 Agent。Graph 只负责可观测的状态路由和工具执行，LLM 不拥有绕过 Tool Guard 的权限。

```text
START
  -> rag_probe
  -> intent_router
       | knowledge       -> no tool
       | realtime_weather -> Weather Tool
       | scenic_info      -> Scenic POI Tool
       | route            -> Route Tool
       | itinerary        -> Itinerary Planner
  -> merge_evidence
END
  -> LLM complete / stream
```

普通 `/chat` 与 `/chat/stream` 共用同一套 LangGraph preparation，因此不会出现两个接口路由逻辑不一致。P1.5 的 `fresh_evidence_required` 会进入实时 Tool 路径，不再直接让静态 RAG 猜测。

## Tool security boundary

Tool 参数先由确定性 Parser 提取，再由 `ToolParameterGuard` 校验长度、控制字符、URL 注入、路线起终点和天气日期范围。LLM 不直接拼接任意 URL，也不能选择未注册 Tool。

## Providers

- Weather: `mock` / Open-Meteo（无 Key）
- Scenic live info: `mock` / 高德 POI 2.0（需要 Web服务 Key）
- Route: `mock` / 高德路径规划 2.0（需要 Web服务 Key）
- Itinerary: 内部确定性约束生成器 + 同轮 RAG 证据

CI 始终设置 `TOOL_MOCK_MODE=true`，只验证 Router、Graph、Guard、Evidence Merge 与 API contract；外部网络质量不会影响 acceptance。生产联调时设置 `TOOL_MOCK_MODE=false` 并配置 `AMAP_API_KEY`。

## Evidence contract

实时 Tool 不把结果直接塞进回答字符串，而是转为 `ToolEvidence`，经过 Evidence Merge 后统一变成 `[C#]` 上下文和 Citation。API 会额外返回 `intent`、`gate_reason`、`tool_calls`，保留 P0/P1 原字段兼容性。

Qwen 仍由 LLM Adapter 负责，模型名完全来自 `LLM_MODEL`；P2 不绑定具体千问型号。
