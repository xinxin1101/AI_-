from __future__ import annotations

import re
from dataclasses import dataclass

from app.tools.base import find_known_places


@dataclass(frozen=True)
class ContextResolution:
    original_query: str
    standalone_query: str
    resolved: bool
    reason: str | None = None
    subject: str | None = None


class ContextResolver:
    def resolve(self, history: list[dict[str, str]], query: str) -> ContextResolution:
        original = query.strip()
        if not original or not history:
            return ContextResolution(original, original, False)

        temporal = re.match(r"^(?:那|那么|那就)?(今天|明天|后天)(?:呢|怎么样|如何)?[？?。！!]*$", original)
        if temporal:
            previous = self._last_user_query(history)
            if previous:
                target = temporal.group(1)
                if re.search(r"今天|明天|后天", previous):
                    rewritten = re.sub(r"今天|明天|后天", target, previous, count=1)
                else:
                    rewritten = f"{target}{previous}"
                return ContextResolution(original, rewritten, True, "temporal_followup", self._last_subject(history))

        ordinal = re.search(r"第([一二三四五六七八九十\d]+)个", original)
        if ordinal:
            subject = self._ordinal_subject(history, ordinal.group(1))
            if subject:
                rewritten = re.sub(r"第[一二三四五六七八九十\d]+个", subject, original, count=1)
                return ContextResolution(original, rewritten, True, "ordinal_reference", subject)

        current_places = find_known_places(original)
        route = re.match(r"^从([^到]+?)(?:怎么过去|怎么去|怎么走|如何过去|如何去|如何走|过去|前往)[？?。！!]*$", original)
        if route:
            subject = self._last_subject(history, exclude=current_places)
            if subject:
                rewritten = f"从{route.group(1)}到{subject}怎么去？"
                return ContextResolution(original, rewritten, True, "route_destination_ellipsis", subject)

        subject = self._last_subject(history)
        if not subject:
            return ContextResolution(original, original, False)

        pronouns = ("那它", "它", "那里", "那边", "这个地方", "那个地方", "这个景点", "那个景点", "刚才那个", "刚才提到的")
        if any(item in original for item in pronouns):
            rewritten = original
            for item in pronouns:
                rewritten = rewritten.replace(item, subject)
            rewritten = re.sub(r"^(那|那么|那就)(?=" + re.escape(subject) + r")", "", rewritten)
            return ContextResolution(original, rewritten, True, "pronoun_reference", subject)

        compact = re.sub(r"\s+", "", original)
        if compact.startswith("附近") and not current_places:
            nearby_short = {"附近", "附近呢", "附近?", "附近？", "附近呢?", "附近呢？"}
            suffix = "附近有什么？" if compact in nearby_short else original
            return ContextResolution(original, f"{subject}{suffix}", True, "nearby_ellipsis", subject)

        if current_places:
            return ContextResolution(original, original, False)

        ellipsis_terms = ("门票", "票价", "开放", "关门", "开门", "营业", "电话", "联系电话", "天气", "下雨", "降雨", "温度", "气温", "值得去", "好玩吗")
        if any(term in compact for term in ellipsis_terms):
            return ContextResolution(original, f"{subject}{original}", True, "subject_ellipsis", subject)

        return ContextResolution(original, original, False)

    @staticmethod
    def _last_user_query(history: list[dict[str, str]]) -> str | None:
        for message in reversed(history):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                content = message["content"].strip()
                if content:
                    return content
        return None

    @staticmethod
    def _last_subject(history: list[dict[str, str]], exclude: list[str] | None = None) -> str | None:
        excluded = set(exclude or [])
        for role in ("user", "assistant"):
            for message in reversed(history):
                if message.get("role") != role:
                    continue
                content = message.get("content")
                if not isinstance(content, str):
                    continue
                places = [place for place in find_known_places(content) if place not in excluded]
                if places:
                    return places[-1]
        return None

    def _ordinal_subject(self, history: list[dict[str, str]], raw: str) -> str | None:
        number_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        index = int(raw) if raw.isdigit() else number_map.get(raw)
        if not index:
            return None
        for role in ("assistant", "user"):
            for message in reversed(history):
                if message.get("role") != role:
                    continue
                content = message.get("content")
                if not isinstance(content, str):
                    continue
                places = find_known_places(content)
                if len(places) >= index:
                    return places[index - 1]
        return None


context_resolver = ContextResolver()
