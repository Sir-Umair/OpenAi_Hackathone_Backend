from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    anthropic_api_key: str | None = None
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "o2n_engine"
    chroma_path: str = "./chroma_data"
    repository_workspace: str = "./repository_workspace"
    cors_origins: str = "http://localhost:3000"

settings = Settings()
