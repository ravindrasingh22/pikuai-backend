from fastapi import APIRouter

from app.data import store
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


@router.get("/messages/{message_id}")
def explain_message(message_id: str) -> dict[str, object]:
    message = store.messages.get(message_id)
    if message is None:
        raise ApiError("NOT_FOUND", "Message explanation was not found.", 404)

    shown_answer = next(
        (
            candidate
            for candidate in store.messages.values()
            if candidate["thread_id"] == message["thread_id"]
            and candidate["sender_type"] == "assistant"
        ),
        None,
    )
    return envelope(
        {
            "message_id": message["id"],
            "child_question": message["message_text"],
            "final_bucket": message["policy_bucket"],
            "age_band": message["age_band_used"],
            "reason_codes": [message["explanation_code"]],
            "explanation_summary": message["explanation_text"],
            "shown_answer": shown_answer["rendered_text"] if shown_answer else "",
        }
    )
