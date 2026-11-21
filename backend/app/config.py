"""Runtime configuration. Every value can be set from the environment or backend/.env.
See SETUP.md for what each one means."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Naqshkaar Catalogue Studio"
    environment: str = "development"

    # --- database -----------------------------------------------------------
    database_url: str = "postgresql+psycopg://naqshkaar:change-me@localhost:5432/naqshkaar_catalogue"
    db_pool_size: int = 10

    # --- security -----------------------------------------------------------
    secret_key: str = "change-me-to-a-long-random-string"
    access_token_minutes: int = 12 * 60
    file_url_ttl_seconds: int = 6 * 60 * 60
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # --- storage ------------------------------------------------------------
    storage_backend: str = "local"            # local | s3
    storage_root: str = "./data/storage"
    s3_endpoint_url: str | None = None        # e.g. http://minio:9000 ; empty for AWS
    s3_bucket: str = "naqshkaar-catalogue"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    # --- uploads and ingest -------------------------------------------------
    max_upload_mb: int = 25
    max_mesh_upload_mb: int = 200
    max_images_per_upload: int = 12
    processed_image_max_side: int = 2048
    thumbnail_side: int = 360
    ingest_auto_create_retailer: bool = True
    ingest_fetch_images: bool = True
    ingest_image_timeout_seconds: float = 20.0

    # --- catalogue rules ----------------------------------------------------
    price_stale_days: int = 30                # advisory only; prices are dated, never assumed live

    # --- asset qualification (NFR-ACC-002 and §6.2) ---------------------------
    # The two tolerance values implement max(0.005 m, 0.01·d). Changing them
    # changes an SRS requirement and needs a recorded SRS revision.
    asset_extent_min_tolerance_m: float = 0.005
    asset_extent_rel_tolerance: float = 0.01
    asset_distortion_warn: float = Field(1.15, description="max/min per-axis scale ratio that triggers a warning")
    asset_distortion_fail: float = Field(1.50, description="ratio treated as severe scaling distortion")
    asset_triangle_budget: int = 300_000
    gltf_validator_cmd: str | None = "node /opt/gltf-validator/validate.mjs"
    require_gltf_validator: bool = False

    # --- jobs and workers ---------------------------------------------------
    job_stale_minutes: int = 20
    asset_processing_stale_minutes: int = 15
    worker_online_seconds: int = 90
    cpu_worker_poll_seconds: float = 3.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
