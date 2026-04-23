from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ThreadMemory:
    short_turns: list[dict[str, str]]
    rolling_summary: str
    unresolved_follow_up: str | None
    emotional_hint: str | None
    recent_entities: list[str]
    observed_preferences: list[str]
    topic_continuity: str

    @property
    def has_recent_context(self) -> bool:
        return len(self.short_turns) > 0


def build_thread_memory(
    recent_messages: list[dict[str, Any]],
    previous_memory: dict[str, Any] | None = None,
) -> ThreadMemory:
    useful_messages = [
        message for message in recent_messages if str(message.get("rendered_text", "")).strip()
    ]
    short_turns = [
        {
            "speaker": str(message.get("sender_type", "child")),
            "text": str(message.get("rendered_text", ""))[:280],
        }
        for message in useful_messages[-8:]
    ]
    recent_entities = _extract_entities(short_turns)
    unresolved_follow_up = _infer_follow_up(short_turns)
    emotional_hint = _infer_emotional_hint(short_turns)
    observed_preferences = _merge_preferences(
        previous_memory.get("observed_preferences", []) if previous_memory else [],
        _infer_preferences(short_turns),
    )
    topic_continuity = _topic_continuity(short_turns, unresolved_follow_up)
    rolling_summary = _rolling_summary(short_turns, recent_entities, unresolved_follow_up, emotional_hint)

    return ThreadMemory(
        short_turns=short_turns[-8:],
        rolling_summary=rolling_summary,
        unresolved_follow_up=unresolved_follow_up,
        emotional_hint=emotional_hint,
        recent_entities=recent_entities,
        observed_preferences=observed_preferences,
        topic_continuity=topic_continuity,
    )


def memory_to_json(memory: ThreadMemory) -> dict[str, Any]:
    return {
        "rolling_summary": memory.rolling_summary,
        "unresolved_follow_up": memory.unresolved_follow_up,
        "emotional_hint": memory.emotional_hint,
        "recent_entities": memory.recent_entities,
        "observed_preferences": memory.observed_preferences,
        "topic_continuity": memory.topic_continuity,
    }


def _extract_entities(turns: list[dict[str, str]]) -> list[str]:
    entities: list[str] = []
    for turn in turns:
        for token in turn["text"].replace("?", " ").replace(",", " ").split():
            lowered = token.lower()
            if lowered in {"sky", "sunset", "fish", "friend", "babies", "night", "dance"} and lowered not in entities:
                entities.append(lowered)
    return entities[:8]


def _infer_follow_up(turns: list[dict[str, str]]) -> str | None:
    for turn in reversed(turns):
        text = turn["text"].lower()
        if "what about" in text or "tell me more" in text or "and then" in text:
            return turn["text"][:120]
    return None


def _infer_emotional_hint(turns: list[dict[str, str]]) -> str | None:
    for turn in reversed(turns):
        text = turn["text"].lower()
        if any(word in text for word in ["scared", "sad", "worried", "afraid", "upset"]):
            return turn["text"][:120]
    return None


def _infer_preferences(turns: list[dict[str, str]]) -> list[str]:
    preferences: list[str] = []
    for turn in turns:
        text = turn["text"].lower()
        if "story" in text and "stories" not in preferences:
            preferences.append("stories")
        if "example" in text and "examples" not in preferences:
            preferences.append("examples")
        if "short" in text and "short_answers" not in preferences:
            preferences.append("short_answers")
    return preferences


def _merge_preferences(existing: list[Any], new: list[str]) -> list[str]:
    merged = [str(item) for item in existing if isinstance(item, str)]
    for item in new:
        if item not in merged:
            merged.append(item)
    return merged[:8]


def _topic_continuity(turns: list[dict[str, str]], unresolved_follow_up: str | None) -> str:
    if unresolved_follow_up:
        return f"Continue prior topic. Pending follow-up: {unresolved_follow_up}"
    if not turns:
        return "Standalone turn."
    return f"Recent topic anchor: {turns[-1]['text'][:100]}"


def _rolling_summary(
    turns: list[dict[str, str]],
    entities: list[str],
    unresolved_follow_up: str | None,
    emotional_hint: str | None,
) -> str:
    if not turns:
        return "No prior thread context."
    parts = [f"Recent turns: {len(turns)}", f"Entities: {', '.join(entities) if entities else 'none'}"]
    if unresolved_follow_up:
        parts.append(f"Pending follow-up: {unresolved_follow_up}")
    if emotional_hint:
        parts.append(f"Emotional hint: {emotional_hint}")
    return " | ".join(parts)
