import asyncio

from app.agent.context import context_resolver
from app.agent.models import Intent
from app.agent.router import classify_intent
from app.agent.service import agent_service
from app.tools.base import find_known_places


def history(*items: tuple[str, str]) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in items]


def test_place_extraction_prefers_longest_non_overlapping_mentions() -> None:
    assert find_known_places("从桂林北站到桂林站") == ["桂林北站", "桂林站"]


def test_resolves_pronoun_for_scenic_followup() -> None:
    result = context_resolver.resolve(
        history(("user", "介绍一下象鼻山"), ("assistant", "象鼻山是桂林代表性景点。")),
        "那它今天几点关门？",
    )
    assert result.resolved is True
    assert result.standalone_query == "象鼻山今天几点关门？"
    assert classify_intent(result.standalone_query) == Intent.SCENIC_INFO


def test_resolves_weather_pronoun() -> None:
    result = context_resolver.resolve(
        history(("user", "我想去阳朔西街"), ("assistant", "可以安排阳朔西街。")),
        "那里明天会下雨吗？",
    )
    assert result.standalone_query == "阳朔西街明天会下雨吗？"
    assert classify_intent(result.standalone_query) == Intent.WEATHER


def test_resolves_route_destination_ellipsis() -> None:
    result = context_resolver.resolve(
        history(("user", "介绍一下象鼻山"), ("assistant", "象鼻山位于桂林市区。")),
        "从桂林北站怎么过去？",
    )
    assert result.standalone_query == "从桂林北站到象鼻山怎么去？"
    assert classify_intent(result.standalone_query) == Intent.ROUTE


def test_resolves_temporal_followup_from_previous_user_query() -> None:
    result = context_resolver.resolve(
        history(("user", "今天桂林天气怎么样？"), ("assistant", "今天可以查看实时天气。")),
        "明天呢？",
    )
    assert result.standalone_query == "明天桂林天气怎么样？"
    assert result.reason == "temporal_followup"


def test_resolves_ordinal_reference_from_assistant_list() -> None:
    result = context_resolver.resolve(
        history(
            ("user", "桂林市区有什么推荐？"),
            ("assistant", "可以考虑象鼻山、两江四湖、独秀峰王城。"),
        ),
        "第二个值得去吗？",
    )
    assert result.standalone_query == "两江四湖值得去吗？"
    assert result.reason == "ordinal_reference"


def test_explicit_new_subject_is_not_rewritten() -> None:
    result = context_resolver.resolve(
        history(("user", "介绍一下象鼻山"), ("assistant", "好的。")),
        "阳朔西街有什么好玩的？",
    )
    assert result.resolved is False
    assert result.standalone_query == "阳朔西街有什么好玩的？"


def test_agent_prepare_routes_on_standalone_query() -> None:
    prepared = asyncio.run(
        agent_service.prepare(
            history(("user", "介绍一下象鼻山"), ("assistant", "象鼻山位于桂林市区。")),
            "那它今天几点关门？",
        )
    )
    assert prepared.context_resolved is True
    assert prepared.standalone_query == "象鼻山今天几点关门？"
    assert prepared.intent == Intent.SCENIC_INFO
