from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App Settings
    LOG_LEVEL: str = "DEBUG"

    # MongoDB
    MONGODB_URL: str = ""
    MONGODB_DB_NAME: str = ""

    # Redis
    REDIS_URL: str = ""

    # Neo4j
    NEO4J_URI: str = ""
    NEO4J_USER: str = ""
    NEO4J_PASSWORD: str = ""

    # LLM Settings
    LLM_PROVIDER: str = "gemini"  # Default to gemini
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768  # valid MRL dimensions: 128, 256, 384, 512, 768, 1536, 2048

    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash-lite"
    GOOGLE_GENAI_USE_VERTEXAI: bool = False


settings = Settings()
