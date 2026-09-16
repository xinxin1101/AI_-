import re

from app.agent.models import Intent


_WEATHER_TERMS = ("天气", "下雨", "降雨", "气温", "温度", "晴", "风力", "会不会下雨")
_SCENIC_TERMS = (
    "开放", "关门", "开门", "营业", "几点开", "几点关", "门票", "票价",
    "暂停", "恢复开放", "联系电话", "电话",
)
_ROUTE_TERMS = ("怎么去", "怎么走", "如何去", "交通", "公交", "步行", "驾车", "开车", "打车", "路线")
_ITINERARY_TERMS = ("行程", "怎么玩", "怎么安排", "安排一下", "几天", "一日游", "两日游", "三日游", "规划")


def classify_intent(query: str, gate_reason: str | None = None) -> Intent:
    text = re.sub(r"\s+", "", query)

    # Multi-day planning is checked before route keywords because itinerary
    # questions often also contain the word "路线".
    if any(term in text for term in _ITINERARY_TERMS):
        return Intent.ITINERARY
    if any(term in text for term in _WEATHER_TERMS):
        return Intent.WEATHER
    if any(term in text for term in _SCENIC_TERMS):
        return Intent.SCENIC_INFO
    if any(term in text for term in _ROUTE_TERMS) or re.search(r"从.+?(到|去).+", text):
        return Intent.ROUTE

    # P1.5 marked the query as requiring fresh evidence but could not classify
    # which live source to use. Scenic-info is the conservative generic live
    # lookup path; weather and route are caught by explicit terms above.
    if gate_reason == "fresh_evidence_required":
        return Intent.SCENIC_INFO
    return Intent.KNOWLEDGE
