from __future__ import annotations

import re


# Retrieval should see the user's tourism question, not a trailing attempt to change
# system behavior. This is intentionally conservative: only split when an obvious
# control-instruction marker occurs after a meaningful prefix. The original user
# message is still sent to the LLM, where system policy remains authoritative.
_TRAILING_CONTROL = re.compile(
    r"(?:另外|此外|并且|然后|顺便)?\s*(?:请)?(?:忽略|无视|绕过|覆盖|忘记)"
    r"(?:之前|以上|所有|任何|当前)?(?:的)?(?:规则|指令|系统指令|提示词|限制)",
    re.IGNORECASE,
)


def retrieval_query(query: str) -> str:
    original = query.strip()
    if not original:
        return original
    match = _TRAILING_CONTROL.search(original)
    if not match or match.start() <= 1:
        return original
    prefix = original[: match.start()].rstrip(" ，,；;。.!！?？")
    return prefix if len(prefix) >= 2 else original
