def parse_tags(text: str) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for raw in (text or "").split(","):
        tag = raw.strip()
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            tags.append(tag)
    return tags


def tags_text(tags) -> str:
    if isinstance(tags, str):
        return tags
    if not isinstance(tags, list):
        return ""
    return ", ".join(str(tag) for tag in tags if str(tag).strip())
