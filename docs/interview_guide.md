# Interview Guide — Guilin Tourism AI Assistant

## 30-second introduction

> 这是一个桂林文旅智能客服的个人重构项目，业务背景来自校企合作场景。我重点重做了 AI 后端，不涉及原来的小程序 UI、支付或票务系统。整体使用 FastAPI + LangGraph + RAG + Qwen，知识侧做 Hybrid Retrieval、RRF、Rerank 和 Citation，实时问题通过受控 Tool 调用天气、路线或景区 Provider；后端用 Redis 做短期会话、PostgreSQL 做 Trace 和消息持久化、Qdrant 做向量检索。最后我不是只做 Demo，而是建立了 30 turns / 24 conversations 的 RC2 真实场景验收集，覆盖多轮、天气、OOD、Prompt Injection 和 Provider failure，修完验收发现的问题后才 Feature Freeze。

## 2-minute architecture answer

> 请求先进入 FastAPI，然后从 Redis 读取最近会话。因为真实多轮里用户经常会说“那它呢”“明天呢”，所以我在 RAG 和 Intent Router 之前增加了一个确定性的 Context Resolver，把支持的省略和指代改写成 standalone query。这个 query 用来做检索、意图分类和 Tool 参数解析，但最终 LLM 仍然看到原始历史和原始问题。
>
> RAG 侧是 Dense abstraction + BM25，然后用 RRF 融合，再经过 rerank 和 confidence/freshness gate。静态知识如果无法支持今天、明天、票价、开放时间等动态问题，就不会直接拿来回答，而是把请求路由到实时 Tool。
>
> Agent 编排使用 LangGraph，Intent 分为 knowledge、weather、scenic、route 和 itinerary。Tool 调用之前有参数 Guard，Provider 层有 timeout、retry 和 circuit breaker。RAG 和 Tool 最终都转换成统一的 Citation evidence，再交给 Qwen 生成。
>
> Redis 只负责短期上下文，PostgreSQL 持久化 conversation、message、feedback、trace、tool_call、citation，Qdrant 做向量检索。可观测侧记录 trace_id、intent、grounded、Tool attempts、latency、token、citation，并提供 Prometheus/OTel 能力。
>
> 最后 RC2 用真实 Qwen、Redis、PostgreSQL、Qdrant 和 Open-Meteo 跑 30 个 turn、24 个 conversation。过程中真的发现了长对话 subject 漂移、Hash Embedding OOD 假 Grounding、实时 Tool 失败后模型编造路线等问题，所以 Feature Freeze 是在这些问题修完、Gate 全绿以后才做的。

## Why LangGraph instead of directly calling the LLM?

Suggested answer:

> 我使用 LangGraph 不是为了“用了 Agent 框架”本身，而是希望把几个必须受控的阶段变成显式节点：Context Resolver、RAG Probe、Intent Router、Tool Branch、Evidence Merge。这样天气问题一定经过 Weather Tool，Tool 参数能在调用前校验，失败时也能走统一 fail-closed，而不是全靠 Prompt 让模型自己决定流程。这个项目里的 LangGraph 更像可观测的执行图，而不是让 LLM 自由循环调用工具。

Follow-up: Why not let LLM classify Intent?

> 当前 Intent 边界比较固定，而且场景是桂林文旅客服，所以我优先用 deterministic router，成本低、可回归、不会因为模型温度导致路由抖动。如果以后 Intent 数量和表达形式大幅增加，可以把 LLM classifier 作为候选，但仍然需要 deterministic policy 对高风险 Tool 做二次约束。

## Why is state separated from prompt context?

> State 是系统执行事实，比如 session_id、standalone_query、intent、tool_calls、citations、gate_reason，不应该依赖模型“记住”。Prompt context 是模型本轮需要看到的信息。把两者分开后，系统状态可以校验、持久化、观测和恢复，而 Prompt 只保留完成当前推理所需的最小信息，也更容易控制 Token。

## Explain the RAG pipeline

> 我把检索拆成 Dense 和 BM25 两路。Dense 负责语义相似，BM25 保留实体名和关键词精确匹配能力，然后通过 RRF 按排名进行融合。融合结果再交给 reranker，最后不是直接 Top-K 塞给模型，而是经过 confidence gate。对开放时间、天气、票价等动态查询还有 freshness gate，静态资料不能冒充实时资料。最终引用被结构化成 Citation，而不是只在 Prompt 里拼文本。

## Why RRF?

> 因为 Dense 和 BM25 的分数尺度不一致，直接加权原始 score 很难统一校准。RRF 只依赖排名，用 `1/(k+rank)` 聚合两路结果，对 score 分布变化不太敏感，适合在工程上快速稳定融合。当前 k=60。

## Why not trust the perfect RC2 metrics?

> RC2 的 100% 是维护验收集全绿，不是线上真实用户准确率。场景集只有 30 turns / 24 conversations，是我有意设计的 release-candidate regression gate，所以 Intent、Tool、Fallback、Trace 这些契约指标冻结时必须是 100%。更有价值的是前面的失败过程：RC2 最初并不是全绿，它暴露了长对话 subject drift、Hash Embedding 对北京故宫假 Grounding、实时 Route Tool 失败后模型编出公交路线等问题。修掉这些具体缺陷之后才达到最终 30/30。

## Explain the Hash Embedding limitation

> Hash Embedding 主要用于 CI 和可重复离线验收，不是生产语义 Embedding。它的优点是不依赖外部模型、速度快、结果稳定，但缺点是语义能力有限，甚至可能出现词特征碰撞。RC2 就发现过 OOD 的北京故宫问题被误判 grounded，所以我给 Hash 模式增加 lexical metadata anchor，避免单靠 dense collision 通过 Gate。真正生产化时我会换成真实 Embedding，再重新做数据集评估，而不是继续依赖这个保护逻辑。

## How do you prevent hallucination?

A good answer should mention layers rather than only Prompt:

> 第一层是检索 confidence/freshness gate，没有证据就不生成；第二层是实时问题必须走 Tool，静态 RAG 不允许替代实时结果；第三层 Tool 参数有 Schema 和 Guard，不让 LLM 任意构造 URL 或越权参数；第四层 Evidence Merge 只把结构化证据交给 LLM；第五层回答要求 Citation；第六层 Provider 失败时 fail-closed。Prompt 只是一层软约束，不是最终安全边界。

## Prompt Injection: front end vs back end

> 前端最多做输入长度、显示转义和明显危险内容提示，不能作为安全边界。后端把 RAG/Search 内容标记为外部不可信文本，并在 Tool 层执行参数、权限和 scope 校验。RC2 还发现“用户正常事实问题 + 尾部忽略规则”会污染检索，所以在 retrieval query 层只移除识别到的尾部控制指令，但不会让这一步替代真正的 Tool security policy。

## Tool parameter ranges: where do they come from?

> 参数范围不是让 LLM 自己生成规则，而是由系统和 Provider contract 决定。例如字符串长度来自 API 约束和安全预算；天气日期范围来自 Provider 能返回的 forecast window；route 起终点必须是正常地点文本且不能是 URL；Tool 名称只能来自 Registry。LLM 最多生成候选参数，是否可执行由代码侧 Guard 决定。

## Provider reliability design

> Provider Client 对 transport error、408、425、429、5xx 做 bounded retry，普通 4xx 和业务认证错误 fail-fast。连续最终失败进入 circuit breaker open，恢复时间到后 half-open 探测。Trace 会记录 attempts、provider latency 和 circuit state。RC2 后面还给天气加入短 TTL forecast reuse，减少同一会话连续查询对公共 Provider 的重复依赖。

## Why Redis and PostgreSQL both?

> Redis 是低延迟短期会话窗口，只保存有限历史并设置 TTL；PostgreSQL 是 durable source，用来保存消息、反馈和可追溯 Trace。这样即使 Redis 淘汰了历史，审计和问题复盘仍然可以依赖 PostgreSQL。把 Redis 当长期数据库会导致审计和一致性边界不清楚。

## Qdrant's role

> Qdrant 只负责向量召回，不负责对话状态、Trace 或业务事务。知识 chunk 的 Dense vector 放在 Qdrant，BM25 当前在应用侧构建，两路结果通过 RRF 融合。

## What is a Trace in this project?

> Trace 是一次请求的结构化执行记录，不只是日志字符串。它关联 session_id、intent、grounded、gate_reason、latency、token、Tool Call、Citation、status/error 等信息。响应里的 application trace_id 也会写进数据库，并作为 OTel span attribute 用于关联，但我不会把它说成 OTel 原生 128-bit Trace ID。

## How is TTFT measured?

> 不是用整个 HTTP 请求时间代替。RC2 真实走 `/chat/stream`，从客户端发起请求开始计时，收到第一个 SSE token event 时记录 TTFT，流结束时记录 end-to-end latency。因此 TTFT 和总延迟是两个独立指标。

Final-head RC2 result:

```text
TTFT P50/P95: 945.780 / 1470.068 ms
E2E P50/P95: 1528.341 / 3369.343 ms
```

These are GitHub-hosted RC baseline values, not an SLA.

## Why did 22 of 30 turns have token metrics?

> 因为有 8 个 turn 走的是 fallback/fail-closed 路径，不需要正常 LLM generation。我的 Token 指标只记录 Provider 实际返回的 usage，不会用字符数去估算一个看似完整的数据。

## Explain the 72.73% raw Tool success rate

> RC2 里有 provider_failure 场景是故意要求 Tool 失败，验证系统能否安全降级，所以 raw Tool success rate 不是 Provider 可用率。真正作为 Gate 的是“应该成功的 Tool 调用是否成功、是否发生重试”，最终 successful-tool retry rate 是 0%。

## What was the hardest bug?

Strong example:

> 我认为最有代表性的是 Route Provider 不可用时，RAG 仍然命中了静态景区资料，所以整个状态还被判为 grounded。结果 LLM 看到了景区上下文以后编出了公交线路、距离和费用。从单模块看，RAG 是正常的、Tool error 也正常，但 Evidence Merge 的语义错了。最后我修改成：只要当前 Intent 需要实时 Tool 且 Tool 失败，就不能让静态 RAG 把这一轮重新变成 grounded，必须 `tool_unavailable` fail-closed。这个问题让我意识到生产 Agent 的错误经常发生在模块之间的组合语义，而不是某一个模型本身。

## Why Feature Freeze after RC2?

> 因为项目已经覆盖了我希望展示的 Agent 应用开发核心能力：RAG、多轮、Tool、Provider reliability、Redis/PostgreSQL/Qdrant、Trace、Eval、安全和部署工程。继续加 P4/P5 功能只会扩大范围，降低简历和面试叙述的清晰度。RC2 全绿以后，我更需要把项目变成可复现 Demo、量化简历和架构讲解，而不是继续堆模块。

## Remaining weaknesses to acknowledge

If the interviewer asks what you would improve next:

> 第一是真实 semantic Embedding 和 reranker 的数据集评估，现在 RC2 仍然是 Hash + local reranker；第二是 AMap 需要真实 credential-backed smoke；第三是场景验收集还可以从 30 turns 扩展到更大的人工标注集，并增加 LLM-as-judge/人工双评估，但要控制 judge bias；第四是如果真上线多实例，我会把 weather cache 和 circuit state 的一致性重新设计，并把部署放到 API Gateway/K8s/managed observability 环境。

This answer shows awareness without pretending those capabilities are already implemented.