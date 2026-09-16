from app.agent.models import ToolEvidence
from app.tools.base import ItineraryInput


class ItineraryPlannerTool:
    name = "itinerary_planner"

    async def get(self, request: ItineraryInput) -> ToolEvidence:
        interests = "、".join(request.interests) if request.interests else "未指定，按当前知识证据选择"
        return ToolEvidence(
            evidence_id="itinerary_constraints",
            tool_name="itinerary_planner",
            title="行程规划约束",
            content=(
                f"规划天数：{request.days} 天；用户明确兴趣点：{interests}。"
                "按天组织上午/下午/晚上，尽量减少跨区域往返；只使用同轮 RAG 证据中的景点事实，"
                "不要编造票价、营业时间或实时交通。"
            ),
            source="Internal deterministic planner",
            freshness_class="static",
            confidence=1.0,
            citable=False,
            metadata={"days": request.days, "interests": request.interests},
        )
