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
    MONGODB_DB_NAME: str = "connect"

    # Redis
    REDIS_URL: str = ""

    # Neo4j
    NEO4J_URI: str = ""
    NEO4J_USER: str = ""
    NEO4J_PASSWORD: str = ""

    # LLM Settings
    LLM_PROVIDER: str = "gemini"  # Options: gemini, openai, ollama
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 768  # valid MRL dimensions: 128, 256, 384, 512, 768, 1536, 2048

    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    GOOGLE_GENAI_USE_VERTEXAI: bool = False

    # Ollama Settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:4b"
    OLLAMA_EMBEDDING_MODEL: str = "qwen3-embedding:0.6b"

    # Connect MCP Server (when run with HTTP transport; avoids conflicting with main FastAPI on 8000)
    MCP_TRANSPORT: str = "stdio"  # stdio | streamable-http
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8001


settings = Settings()
