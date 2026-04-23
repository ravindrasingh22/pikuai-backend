from app.modules.chat.age_style_rules import age_style_instruction
from app.modules.chat.message_classifier import classify_message
from app.modules.chat.prompt_builder import PromptBuildInput, build_prompts
from app.modules.chat.safety_response_policy import select_answer_mode
from app.modules.chat.thread_memory_manager import build_thread_memory


def test_message_classification_examples() -> None:
    assert classify_message("Why is the sky blue?", "6-8", False) == "factual_learning"
    assert classify_message("Can you dance?", "3-5", False) == "imaginative_play"
    assert classify_message("Do fish get thirsty?", "9-11", False) == "factual_learning"
    assert classify_message("My friend is not talking to me.", "9-11", False) == "social_relationship"
    assert classify_message("Where do babies come from?", "3-5", False) == "risky_sensitive"
    assert classify_message("I feel scared.", "6-8", False) == "emotional_support"


def test_answer_mode_selection() -> None:
    assert select_answer_mode(None, "factual_learning", "allowed") == "guided_learning"
    assert select_answer_mode(None, "emotional_support", "allowed") == "comforting"
    assert select_answer_mode(None, "imaginative_play", "allowed") == "playful"
    assert select_answer_mode("quick_answer", "social_relationship", "allowed") == "quick_answer"
    assert select_answer_mode(None, "risky_sensitive", "block_and_redirect") == "parent_safe_redirect"


def test_age_style_instruction_by_band() -> None:
    assert "1-3 short sentences" in age_style_instruction("3-5")
    assert "tiny relatable example" in age_style_instruction("6-8")
    assert "did you know" in age_style_instruction("9-11")


def test_prompt_builder_includes_memory_and_safety_context() -> None:
    memory = build_thread_memory(
        [
            {"sender_type": "child", "rendered_text": "Why is the sky blue?"},
            {"sender_type": "assistant", "rendered_text": "Blue light scatters more in air."},
            {"sender_type": "child", "rendered_text": "What about sunset?"},
        ],
        None,
    )
    prompts = build_prompts(
        PromptBuildInput(
            child_name="Anaya",
            child_age_group="6-8",
            child_gender="girl",
            child_pattern="curious",
            language="en",
            policy_bucket="allowed",
            safety_category="general_learning",
            answer_mode="guided_learning",
            message_category="follow_up_question",
            message="What about sunset?",
            memory=memory,
        )
    )
    assert len(prompts) == 2
    system_prompt = prompts[0]["content"]
    user_prompt = prompts[1]["content"]
    assert "Answer the child's actual question first" in system_prompt
    assert "Age policy" in system_prompt
    assert "Thread memory:" in user_prompt
    assert "Current child message:" in user_prompt
    assert "policy_bucket: allowed" in user_prompt
