from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost/mxwhisper"
    temporal_host: str = "localhost:7233"
    upload_dir: str = "uploads"
    max_file_size: int = 1 * 1024 * 1024 * 1024  # 1GB
    
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
    
    # Test token for API verification
    test_token: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()