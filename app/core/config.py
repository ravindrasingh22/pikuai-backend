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
    jwt_secret: str = "change-me-in-local-env"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 14400
    refresh_token_days: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
