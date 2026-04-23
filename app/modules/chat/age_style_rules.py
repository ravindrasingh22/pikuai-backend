from dataclasses import dataclass


@dataclass(frozen=True)
class AgeStyleRule:
    age_band: str
    max_sentences: int
    depth_guidance: str
    format_guidance: str


AGE_STYLE_RULES: dict[str, AgeStyleRule] = {
    "3-5": AgeStyleRule(
        age_band="3-5",
        max_sentences=3,
        depth_guidance="Use very short, concrete language. Avoid abstractions and jargon.",
        format_guidance="1-3 short sentences.",
    ),
    "6-8": AgeStyleRule(
        age_band="6-8",
        max_sentences=4,
        depth_guidance="Give a simple explanation and one tiny relatable example.",
        format_guidance="Short answer plus one small example.",
    ),
    "9-11": AgeStyleRule(
        age_band="9-11",
        max_sentences=5,
        depth_guidance="Explain clearly and add one curiosity extension when useful.",
        format_guidance="Answer + one optional 'did you know' extension.",
    ),
    "11-13": AgeStyleRule(
        age_band="11-13",
        max_sentences=6,
        depth_guidance="Give fuller explanation with clear logic while staying safe.",
        format_guidance="Concise but detailed enough for middle-school curiosity.",
    ),
    "14-17": AgeStyleRule(
        age_band="14-17",
        max_sentences=7,
        depth_guidance="Use respectful teen-level clarity. Be honest, concise, and safe.",
        format_guidance="Direct explanation with mature but protected framing.",
    ),
}


def normalize_age_band(age_band: str) -> str:
    return age_band if age_band in AGE_STYLE_RULES else "9-11"


def age_style_rule(age_band: str) -> AgeStyleRule:
    return AGE_STYLE_RULES[normalize_age_band(age_band)]


def age_style_instruction(age_band: str) -> str:
    rule = age_style_rule(age_band)
    return (
        f"Age policy for {rule.age_band}: {rule.depth_guidance} "
        f"Output format: {rule.format_guidance} "
        f"Do not exceed {rule.max_sentences} sentences unless safety requires a short redirect."
    )
