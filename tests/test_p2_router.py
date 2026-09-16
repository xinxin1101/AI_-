from app.agent.models import Intent
from app.agent.router import classify_intent


def test_router_classifies_core_intents() -> None:
    assert classify_intent("介绍一下象鼻山") == Intent.KNOWLEDGE
    assert classify_intent("明天去漓江会下雨吗？") == Intent.WEATHER
    assert classify_intent("象鼻山今天几点关门？") == Intent.SCENIC_INFO
    assert classify_intent("从桂林北站到阳朔西街怎么走？") == Intent.ROUTE
    assert classify_intent("桂林两天怎么玩，帮我安排行程") == Intent.ITINERARY


def test_freshness_gate_routes_generic_live_query_to_scenic_tool() -> None:
    assert classify_intent("现在情况怎么样？", "fresh_evidence_required") == Intent.SCENIC_INFO
