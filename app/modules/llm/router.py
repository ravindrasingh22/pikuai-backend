from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import require_admin
from app.modules.llm.client import get_llm_runtime_config, llm_public_config, update_llm_runtime_config
from app.shared.envelope import envelope
from app.shared.exceptions import ApiError

router = APIRouter()


class LlmConfigPatch(BaseModel):
    enabled: bool | None = None
    provider: str | None = Field(default=None, pattern="^(ollama|openai_compatible)$")
    base_url: str | None = None
    model: str | None = None
    api_key_optional: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0, le=300)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=32, le=4096)
    system_prompt_template: str | None = None
    user_prompt_template: str | None = None


@router.get("/config")
def get_llm_config() -> dict[str, object]:
    return envelope(llm_public_config())


@router.patch("/config", dependencies=[Depends(require_admin)])
def patch_llm_config(payload: LlmConfigPatch) -> dict[str, object]:
    updates = payload.model_dump(exclude_unset=True)
    if "base_url" in updates and not str(updates["base_url"]).strip():
        raise ApiError("INVALID_LLM_CONFIG", "LLM base URL cannot be empty.", 422)
    if "model" in updates and not str(updates["model"]).strip():
        raise ApiError("INVALID_LLM_CONFIG", "LLM model cannot be empty.", 422)
    if "system_prompt_template" in updates and "{message}" not in str(updates["system_prompt_template"]):
        # The user prompt may carry the child question; requiring it in either template keeps configuration usable.
        user_template = str(updates.get("user_prompt_template") or get_llm_runtime_config()["user_prompt_template"])
        if "{message}" not in user_template:
            raise ApiError("INVALID_LLM_CONFIG", "Prompt templates must include the {message} placeholder.", 422)
    if "user_prompt_template" in updates and "{message}" not in str(updates["user_prompt_template"]):
        system_template = str(updates.get("system_prompt_template") or get_llm_runtime_config()["system_prompt_template"])
        if "{message}" not in system_template:
            raise ApiError("INVALID_LLM_CONFIG", "Prompt templates must include the {message} placeholder.", 422)
    return envelope(update_llm_runtime_config(updates), "LLM configuration updated.")
