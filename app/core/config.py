from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    node_env: str = "development"
    port: int = 4000
    admin_origin: str = "http://localhost:5173"
    cors_origins: str = ""
    database_url: str = "postgresql://pikuai:pikuai_password@localhost:5432/pikuai"
    llm_provider: str = "ollama"
    llm_enabled: bool = True
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "mistral:latest"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 30
    llm_temperature: float = 0.2
    llm_max_tokens: int = 280
    guardrails_enabled: bool = True
    guardrails_text_normalization_enabled: bool = True
    guardrails_text_normalization_url: str = "http://localhost:4002/api/v1/guardrail/text-normalization"
    guardrails_text_normalization_system_prompt: str = (
        "Normalize the child's message for downstream safety classification. "
        "Fix obvious typos, spacing, casing, and punctuation while preserving the child's meaning, language, and safety signals."
    )
    guardrails_classified_prompt_enabled: bool = True
    guardrails_classified_prompt_url: str = "http://localhost:4001/api/v1/guardrail/classified/prompt"
    guardrails_chat_url: str = "http://localhost:4003/api/v1/guardrail/chat"
    guardrails_default_system_prompt: str = (
        "You are PikuAI, a child-safe learning assistant. Answer warmly, briefly, and age-appropriately. "
        "Do not provide harmful, exploitative, sexual, violent, or unsafe instructions. Redirect unsafe requests safely."
    )
    guardrails_validator_enabled: bool = True
    guardrails_validator_url: str = "http://localhost:4002/api/v1/guardrail/validate"
    guardrails_validator_threshold: float = 0.85
    guardrails_fallback_response: str = "I can't help with that, but I can help with something safe or talk through what is worrying you."
    guardrails_timeout_seconds: float = 30
    jwt_secret: str = "change-me-in-local-env"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 14400
    refresh_token_days: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
