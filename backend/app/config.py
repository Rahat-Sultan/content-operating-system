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
    # Google sign-in (OAuth 2.0). Both must be set to enable the Google option.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    frontend_url: str = "http://localhost:3000"
    # Supabase Storage for post images. The secret key is server-only and never reaches the browser.
    supabase_url: str = ""
    supabase_secret_key: str = ""
    supabase_bucket: str = "post-image"
    user_storage_limit_mb: int = 50
    # SMTP for transactional email (password reset codes). All four must be set to send
    # real email; without them the code is logged instead, for local development.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "Content OS <no-reply@content-os.local>"
    smtp_use_tls: bool = True


settings = Settings()
