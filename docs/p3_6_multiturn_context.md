# P3.6 Multi-turn Context Resolution

## Goal

P3.5 already stored recent conversation history and passed that history to the LLM. The remaining gap was that RAG retrieval, intent routing and tool parameter parsing still used only the latest user query. P3.6 adds a deterministic context-resolution layer before those components.

```text
Recent Session History
        +
Current User Query
        ↓
Context Resolver
        ↓
Standalone Query
        ↓
RAG Probe
        ↓
Intent Router
        ↓
Tool Parameter Guard / Tool
        ↓
Evidence Merge
        ↓
LLM receives original query + original history + evidence
```

The rewritten query is used for retrieval/routing/tool execution only. The final LLM still sees the original conversational wording, so the reply remains natural.

## Supported deterministic follow-ups

The resolver intentionally targets common tourism-customer-service ellipsis instead of trying to become a general coreference model. Current rules cover:

- pronouns: `它` / `那里` / `那边` / `这个景点` / `刚才那个`
- omitted subject: `票价呢？` / `今天几点关门？` / `温度呢？`
- nearby ellipsis: `附近呢？`
- time continuation: `明天呢？` / `后天呢？`
- missing route destination: `从桂林北站怎么过去？`
- ordinal references to the latest recommendation list: `第二个值得去吗？`

Examples:

```text
历史：介绍一下象鼻山
当前：那它今天几点关门？
Standalone：象鼻山今天几点关门？
```

```text
历史：介绍一下象鼻山
当前：从桂林北站怎么过去？
Standalone：从桂林北站到象鼻山怎么去？
```

```text
历史：今天桂林天气怎么样？
当前：明天呢？
Standalone：明天桂林天气怎么样？
```

## Conservative behavior

The resolver does not call an LLM. If it cannot recover a supported subject from recent history it leaves the query unchanged instead of inventing one. Explicit new entities in the current query also take precedence over old history.

Known tourism place matching uses longest non-overlapping spans so `桂林北站` is not accidentally reduced to the shorter nested token `桂林`.

## API observability

`POST /api/v1/chat` now includes:

```json
{
  "standalone_query": "象鼻山今天几点关门？",
  "context_resolved": true,
  "context_resolution_reason": "pronoun_reference"
}
```

The same metadata is emitted in `/chat/stream` SSE `meta` events. These fields are intended for debugging and evaluation; clients should still display the user's original message.

## Multi-turn Eval

Dataset:

```text
eval/multiturn_eval.jsonl
```

Run:

```bash
python -m scripts.eval_multiturn --fail-on-threshold
```

Metrics:

- standalone query exact accuracy
- resolved/not-resolved flag accuracy
- contextual-case query accuracy
- downstream intent accuracy
- downstream tool-selection accuracy

Because this is a deterministic regression set, CI requires all metrics to be `1.0`. This is not a claim of 100% production coreference accuracy; it only means every maintained regression case passes.

## Scope boundary

P3.6 is intentionally the final functional increment before release-candidate validation. It does not add long-term semantic memory, general-purpose entity linking, LLM-based query rewriting, or new tourism tools. Ambiguous open-domain references should remain unresolved rather than being guessed.
