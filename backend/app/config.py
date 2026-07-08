from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./buildingbills.db"
    secret_key: str = "change-me-in-production"
    token_expire_minutes: int = 60 * 24
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mail_from: str = "bills@building.local"
    storage_dir: str = "./storage"
    notifier: str = "email"  # email | console

    class Config:
        env_file = ".env"


settings = Settings()
