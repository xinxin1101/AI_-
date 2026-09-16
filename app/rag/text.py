import re


_PART_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)
_STOPWORDS = {
    "的", "了", "吗", "呢", "是", "在", "去", "到", "我", "你", "他", "她",
    "有", "和", "与", "及", "想", "请", "问", "怎么", "如何", "哪里", "什么",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def tokenize(text: str) -> list[str]:
    """Small dependency-free tokenizer suitable for deterministic CI and BM25.

    Chinese spans are expanded into character and bi-gram features. Production
    semantic retrieval is expected to use a real embedding provider; this tokenizer
    is intentionally lexical and deterministic.
    """
    tokens: list[str] = []
    for part in _PART_RE.findall(normalize_text(text)):
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            if part not in _STOPWORDS:
                tokens.append(part)
            for char in part:
                if char not in _STOPWORDS:
                    tokens.append(char)
            for index in range(len(part) - 1):
                gram = part[index : index + 2]
                if gram not in _STOPWORDS:
                    tokens.append(gram)
        else:
            tokens.append(part)
    return tokens
