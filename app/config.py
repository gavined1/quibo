from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    webhook_secret: str

    llm_base_url: str
    llm_api_key: str
    llm_model: str

    supabase_url: str
    supabase_key: str

    public_url: str

    rate_limit_max: int = 5
    rate_limit_window: int = 60
