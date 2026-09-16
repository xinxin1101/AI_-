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

        current_places = find_known_places(original)
        subject = self._last_subject(history)
        if not subject:
            return ContextResolution(original, original, False)

        pronouns = ("它", "那里", "那边", "这个景点", "那个景点", "刚才那个")
        if any(item in original for item in pronouns):
            rewritten = original
            for item in pronouns:
                rewritten = rewritten.replace(item, subject)
            rewritten = re.sub(r"^(那|那么|那就)(?=" + re.escape(subject) + r")", "", rewritten)
            return ContextResolution(original, rewritten, True, "pronoun_reference", subject)

        compact = re.sub(r"\s+", "", original)
        if compact.startswith("附近") and not current_places:
            suffix = "附近有什么？" if compact in {"附近", "附近呢", "附近?", "附近？"} else original
            return ContextResolution(original, f"{subject}{suffix}", True, "nearby_ellipsis", subject)

        if current_places:
            return ContextResolution(original, original, False)

        ellipsis_terms = ("门票", "票价", "开放", "关门", "开门", "营业", "电话", "天气", "下雨", "温度")
        if any(term in compact for term in ellipsis_terms):
            return ContextResolution(original, f"{subject}{original}", True, "subject_ellipsis", subject)

        return ContextResolution(original, original, False)

    @staticmethod
    def _last_subject(history: list[dict[str, str]]) -> str | None:
        for role in ("user", "assistant"):
            for message in reversed(history):
                if message.get("role") != role:
                    continue
                content = message.get("content")
                if not isinstance(content, str):
                    continue
                places = find_known_places(content)
                if places:
                    return places[-1]
        return None


context_resolver = ContextResolver()
