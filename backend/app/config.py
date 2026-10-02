from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    openrouter_api_key: str = ""
    environment: str = "development"
    publisher_provider: str = "local"
    buffer_access_token: str = ""
    buffer_profile_id: str = ""


settings = Settings()
