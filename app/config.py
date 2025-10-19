from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost/mxwhisper"
    temporal_host: str = "localhost:7233"
    upload_dir: str = "uploads"
    max_file_size: int = 1 * 1024 * 1024 * 1024  # 1GB

    # Whisper Configuration
    whisper_model_size: str = "base"  # Options: tiny, base, small, medium, large

    # Semantic Chunking Configuration
    enable_semantic_chunking: bool = True
    chunking_strategy: str = "ollama"  # Options: ollama, sentence, simple

    # Ollama Configuration (also supports vLLM and OpenAI-compatible endpoints)
    ollama_base_url: str = "http://fedora.mixwarecs-home.net:8000"
    ollama_model: str = "hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4"
    ollama_timeout: int = 300  # seconds (total timeout) - increased from 120
    ollama_max_retries: int = 3
    ollama_connect_timeout: int = 60  # seconds - increased from 30
    ollama_read_timeout: int = 240  # seconds - increased from 90

    # Chunk Settings
    chunk_min_tokens: int = 200
    chunk_max_tokens: int = 500
    chunk_overlap_tokens: int = 50

    # Heartbeat Settings (for Temporal activities)
    activity_heartbeat_interval: int = 5  # seconds between automatic heartbeats
    activity_heartbeat_timeout: int = 300  # 5 minutes - max time without heartbeat

    # Authentik Configuration
    authentik_server_url: str = ""
    authentik_client_id: str = ""
    authentik_client_secret: str = ""
    authentik_issuer_url: str = ""
    authentik_jwks_url: str = ""
    authentik_expected_issuer: str = ""
    authentik_expected_audience: str = ""
    authentik_scopes: str = "openid profile email"
    # Authentik API Configuration (for admin operations)
    authentik_api_url: str = ""
    authentik_admin_token: str = ""  # Admin token for API access

    # Token Configuration
    default_token_expiry_days: int = 365  # Default token expiration in days (1 year)

    # Service Account JWT Configuration
    # These are self-signed JWTs for API access without OAuth2 web login
    service_account_jwt_secret: str = "change-this-secret-key-in-production"  # Secret key for signing service account JWTs
    service_account_jwt_algorithm: str = "HS256"  # Algorithm for service account JWTs

    # Test token for API verification
    test_token: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env that aren't defined in Settings

settings = Settings()