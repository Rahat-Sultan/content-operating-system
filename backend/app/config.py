from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    openrouter_api_key: str = ""
    environment: str = "development"
    publisher_provider: str = "local"
    buffer_access_token: str = ""
    buffer_profile_id: str = ""
    # Public HTTPS base URL where media files are reachable. Buffer fetches images from
    # this URL itself, so localhost will never work. Example: https://media.example.com
    media_public_base_url: str = ""
    # Fernet key that encrypts API keys saved from the Settings page. Required to save keys.
    settings_encryption_key: str = ""


settings = Settings()
