from collections.abc import AsyncIterator

from langgraph.graph import END, START, StateGraph

from app.agent.context import context_resolver
from app.agent.models import AgentPrepared, AgentState, Intent, ToolEvent, ToolEvidence
from app.agent.router import classify_intent
from app.core.config import Settings, get_settings
from app.rag.models import Citation, RAGResult
from app.rag.service import LOW_CONFIDENCE_ANSWER, rag_service
from app.security.prompt_guard import retrieval_query
from app.services.llm import LLMClient, llm_client
from app.tools.base import (
    ToolExecutionError,
    ToolParameterGuard,
    parse_itinerary_input,
    parse_route_input,
    parse_scenic_input,
    parse_weather_input,
)
from app.tools.registry import ToolRegistry, tool_registry


TOOL_UNAVAILABLE_ANSWER = (
    "当前实时服务暂时无法提供可靠结果，我不会用静态资料猜测实时信息。"
    "你可以稍后重试，或以景区、天气和地图官方渠道的最新信息为准。"
)
_REALTIME_TOOL_INTENTS = {
    Intent.WEATHER.value,
    Intent.SCENIC_INFO.value,
    Intent.ROUTE.value,
}


class AgentService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        tools: ToolRegistry | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.tools = tools or tool_registry
        self.llm = llm or llm_client
        self.guard = ToolParameterGuard(self.settings)
        self.graph = self._build_graph()

    @staticmethod
    def _active_query(state: AgentState) -> str:
        return state.get("standalone_query") or state["query"]

    async def _resolve_context(self, state: AgentState) -> dict:
        resolution = context_resolver.resolve(state.get("history", []), state["query"])
        return {
            "standalone_query": resolution.standalone_query,
            "context_resolved": resolution.resolved,
            "context_resolution_reason": resolution.reason,
        }

    async def _rag_probe(self, state: AgentState) -> dict:
        query = retrieval_query(self._active_query(state))
        return {"rag_result": await rag_service.retrieve(query)}

    async def _route_intent(self, state: AgentState) -> dict:
        rag_result = state.get("rag_result")
        gate_reason = rag_result.gate_reason if rag_result else None
        return {"intent": classify_intent(self._active_query(state), gate_reason).value}

    @staticmethod
    def _route_after_intent(state: AgentState) -> str:
        return state.get("intent", Intent.KNOWLEDGE.value)

    @staticmethod
    def _success_event(
        tool_name: str,
        provider: str,
        evidence: ToolEvidence,
    ) -> ToolEvent:
        metadata = evidence.metadata
        attempts = metadata.get("provider_attempts")
        latency_ms = metadata.get("provider_latency_ms")
        circuit_state = metadata.get("circuit_state")
        return ToolEvent(
            tool_name=tool_name,
            status="success",
            provider=provider,
            summary=evidence.title,
            attempts=attempts if isinstance(attempts, int) and attempts >= 1 else None,
            latency_ms=(
                float(latency_ms)
                if isinstance(latency_ms, (int, float)) and latency_ms >= 0
                else None
            ),
            circuit_state=(
                str(circuit_state)
                if isinstance(circuit_state, str) and circuit_state
                else None
            ),
        )

    async def _knowledge(self, state: AgentState) -> dict:
        return {"tool_evidence": [], "tool_calls": []}

    async def _weather(self, state: AgentState) -> dict:
        try:
            params = self.guard.weather(parse_weather_input(self._active_query(state)))
            evidence = await self.tools.weather.get(params)
            event = self._success_event("weather", self.tools.weather.name, evidence)
            return {"tool_evidence": [evidence], "tool_calls": [event]}
        except (ToolExecutionError, ValueError) as exc:
            return {
                "tool_evidence": [],
                "tool_calls": [
                    ToolEvent(
                        tool_name="weather",
                        status="error",
                        provider=getattr(self.tools.weather, "name", "unknown"),
                        summary=str(exc),
                    )
                ],
            }

    async def _scenic(self, state: AgentState) -> dict:
        try:
            params = self.guard.scenic(parse_scenic_input(self._active_query(state)))
            evidence = await self.tools.scenic.get(params)
            event = self._success_event("scenic_info", self.tools.scenic.name, evidence)
            return {"tool_evidence": [evidence], "tool_calls": [event]}
        except (ToolExecutionError, ValueError) as exc:
            return {
                "tool_evidence": [],
                "tool_calls": [
                    ToolEvent(
                        tool_name="scenic_info",
                        status="error",
                        provider=getattr(self.tools.scenic, "name", "unknown"),
                        summary=str(exc),
                    )
                ],
            }

    async def _route_tool(self, state: AgentState) -> dict:
        try:
            params = self.guard.route(parse_route_input(self._active_query(state)))
            evidence = await self.tools.route.get(params)
            event = self._success_event("route", self.tools.route.name, evidence)
            return {"tool_evidence": [evidence], "tool_calls": [event]}
        except (ToolExecutionError, ValueError) as exc:
            return {
                "tool_evidence": [],
                "tool_calls": [
                    ToolEvent(
                        tool_name="route",
                        status="error",
                        provider=getattr(self.tools.route, "name", "unknown"),
                        summary=str(exc),
                    )
                ],
            }

    async def _itinerary(self, state: AgentState) -> dict:
        try:
            params = parse_itinerary_input(self._active_query(state))
            evidence = await self.tools.itinerary.get(params)
            event = self._success_event(
                "itinerary_planner",
                self.tools.itinerary.name,
                evidence,
            )
            return {"tool_evidence": [evidence], "tool_calls": [event]}
        except (ToolExecutionError, ValueError) as exc:
            return {
                "tool_evidence": [],
                "tool_calls": [
                    ToolEvent(
                        tool_name="itinerary_planner",
                        status="error",
                        provider=self.tools.itinerary.name,
                        summary=str(exc),
                    )
                ],
            }

    async def _merge_evidence(self, state: AgentState) -> dict:
        rag_result: RAGResult = state.get("rag_result") or RAGResult(
            grounded=False,
            confidence=0.0,
        )
        evidence: list[ToolEvidence] = state.get("tool_evidence", [])
        citations = list(rag_result.citations) if rag_result.grounded else []
        context_blocks = [rag_result.context] if rag_result.grounded and rag_result.context else []
        confidence = rag_result.confidence if rag_result.grounded else 0.0
        citable_tool_evidence = False

        for item in evidence:
            if item.citable:
                citable_tool_evidence = True
                citation_id = f"C{len(citations) + 1}"
                citations.append(
                    Citation(
                        citation_id=citation_id,
                        document_id=f"tool:{item.tool_name}:{item.evidence_id}",
                        chunk_id=item.evidence_id,
                        title=item.title,
                        source=item.source,
                        source_url=item.source_url,
                        updated_at=item.observed_at,
                        observed_at=item.observed_at,
                        snippet=item.content[: self.settings.rag_citation_snippet_chars],
                        source_type="tool",
                        tool_name=item.tool_name,
                    )
                )
                context_blocks.append(
                    f"[{citation_id}] 实时工具：{item.tool_name}\n"
                    f"来源：{item.source}\n"
                    f"内容：{item.content}\n"
                )
                confidence = max(confidence, item.confidence)
            else:
                context_blocks.append(f"[规划约束]\n{item.content}\n")

        tool_calls = state.get("tool_calls", [])
        has_tool_error = any(item.status == "error" for item in tool_calls)
        realtime_tool_failed = (
            state.get("intent") in _REALTIME_TOOL_INTENTS
            and has_tool_error
            and not citable_tool_evidence
        )

        # A failed live tool must override static RAG evidence for realtime intents.
        # Otherwise a route/opening-time failure can accidentally authorize the LLM
        # to invent current transport, price or opening details from unrelated static
        # attraction documents.
        if realtime_tool_failed:
            return {
                "context": "",
                "citations": [],
                "grounded": False,
                "confidence": 0.0,
                "gate_reason": "tool_unavailable",
                "fallback_answer": TOOL_UNAVAILABLE_ANSWER,
            }

        grounded = rag_result.grounded or citable_tool_evidence
        if citable_tool_evidence:
            gate_reason = "tool_evidence"
        elif rag_result.grounded:
            gate_reason = rag_result.gate_reason or "grounded"
        elif has_tool_error:
            gate_reason = "tool_unavailable"
        else:
            gate_reason = rag_result.gate_reason or "low_confidence"
        fallback = TOOL_UNAVAILABLE_ANSWER if has_tool_error else LOW_CONFIDENCE_ANSWER
        return {
            "context": "\n".join(block for block in context_blocks if block),
            "citations": citations,
            "grounded": grounded,
            "confidence": max(0.0, min(1.0, confidence)),
            "gate_reason": gate_reason,
            "fallback_answer": fallback,
        }

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("context_resolver", self._resolve_context)
        builder.add_node("rag_probe", self._rag_probe)
        builder.add_node("intent_router", self._route_intent)
        builder.add_node(Intent.KNOWLEDGE.value, self._knowledge)
        builder.add_node(Intent.WEATHER.value, self._weather)
        builder.add_node(Intent.SCENIC_INFO.value, self._scenic)
        builder.add_node(Intent.ROUTE.value, self._route_tool)
        builder.add_node(Intent.ITINERARY.value, self._itinerary)
        builder.add_node("merge_evidence", self._merge_evidence)
        builder.add_edge(START, "context_resolver")
        builder.add_edge("context_resolver", "rag_probe")
        builder.add_edge("rag_probe", "intent_router")
        builder.add_conditional_edges(
            "intent_router",
            self._route_after_intent,
            {
                Intent.KNOWLEDGE.value: Intent.KNOWLEDGE.value,
                Intent.WEATHER.value: Intent.WEATHER.value,
                Intent.SCENIC_INFO.value: Intent.SCENIC_INFO.value,
                Intent.ROUTE.value: Intent.ROUTE.value,
                Intent.ITINERARY.value: Intent.ITINERARY.value,
            },
        )
        for node in Intent:
            builder.add_edge(node.value, "merge_evidence")
        builder.add_edge("merge_evidence", END)
        return builder.compile()

    async def prepare(
        self,
        history: list[dict[str, str]],
        query: str,
    ) -> AgentPrepared:
        if not self.settings.agent_enabled:
            resolution = context_resolver.resolve(history, query)
            rag_result = await rag_service.retrieve(resolution.standalone_query)
            return AgentPrepared(
                intent=Intent.KNOWLEDGE,
                grounded=rag_result.grounded,
                confidence=rag_result.confidence,
                context=rag_result.context,
                citations=rag_result.citations,
                gate_reason=rag_result.gate_reason,
                fallback_answer=LOW_CONFIDENCE_ANSWER,
                standalone_query=resolution.standalone_query,
                context_resolved=resolution.resolved,
                context_resolution_reason=resolution.reason,
            )

        state = await self.graph.ainvoke({"query": query, "history": history})
        return AgentPrepared(
            intent=Intent(state.get("intent", Intent.KNOWLEDGE.value)),
            grounded=bool(state.get("grounded", False)),
            confidence=float(state.get("confidence", 0.0)),
            context=state.get("context", ""),
            citations=state.get("citations", []),
            tool_calls=state.get("tool_calls", []),
            gate_reason=state.get("gate_reason"),
            fallback_answer=state.get("fallback_answer", LOW_CONFIDENCE_ANSWER),
            standalone_query=state.get("standalone_query", query),
            context_resolved=bool(state.get("context_resolved", False)),
            context_resolution_reason=state.get("context_resolution_reason"),
        )

    @staticmethod
    def _ensure_single_citation(answer: str, prepared: AgentPrepared) -> str:
        if len(prepared.citations) != 1 or "[C" in answer:
            return answer
        return f"{answer.rstrip()} [{prepared.citations[0].citation_id}]"

    async def complete(
        self,
        history: list[dict[str, str]],
        query: str,
    ) -> tuple[AgentPrepared, str]:
        prepared = await self.prepare(history, query)
        if not prepared.can_generate:
            return prepared, prepared.fallback_answer or LOW_CONFIDENCE_ANSWER
        answer = await self.llm.complete(history, query, context=prepared.context)
        return prepared, self._ensure_single_citation(answer, prepared)

    async def stream(
        self,
        prepared: AgentPrepared,
        history: list[dict[str, str]],
        query: str,
    ) -> AsyncIterator[str]:
        if not prepared.can_generate:
            text = prepared.fallback_answer or LOW_CONFIDENCE_ANSWER
            for index in range(0, len(text), 12):
                yield text[index : index + 12]
            return
        saw_citation = False
        async for chunk in self.llm.stream(history, query, context=prepared.context):
            if "[C" in chunk:
                saw_citation = True
            yield chunk
        if len(prepared.citations) == 1 and not saw_citation:
            yield f" [{prepared.citations[0].citation_id}]"


agent_service = AgentService()
