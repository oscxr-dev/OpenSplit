from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder defaults that must never be used in production.
_INSECURE_DEFAULTS = {
    "jwt_secret": "change-me-in-production-use-openssl-rand-hex-32",
    "lnbits_webhook_secret": "change-me-webhook-secret",
    "seed_admin_password": "change-me-in-production",
}

# Hostnames that only resolve on the operator's own machine/Docker host. A
# public_base_url pointing at one of these can never receive real webhooks.
_LOCAL_ONLY_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORCHESTRATOR_", case_sensitive=False)

    # Runtime
    environment: str = "development"  # development | staging | production

    # Database
    db_url: str = "postgresql+asyncpg://lnbits:lnbits@postgres:5432/orchestrator"

    # Auth
    jwt_secret: str = _INSECURE_DEFAULTS["jwt_secret"]
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    jwt_refresh_days: int = 7

    # LNBits
    lnbits_internal_url: str = "http://lnbits:5000"
    lnbits_webhook_secret: str = _INSECURE_DEFAULTS["lnbits_webhook_secret"]

    # Seed
    seed_admin_password: str = _INSECURE_DEFAULTS["seed_admin_password"]

    # Public base URL of THIS orchestrator as external services reach it —
    # used to compose the BTCPay webhook delivery URL shown to the operator.
    # The localhost default only works when BTCPay runs on the same host.
    public_base_url: str = "http://localhost:8000"

    # CORS — comma-separated list of allowed origins. Defaults to local dev only.
    # In production this MUST be set explicitly via ORCHESTRATOR_CORS_ORIGINS.
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Nostr proof signing key (nsec or 64-hex), held in memory only — NEVER
    # persisted anywhere by this application. Empty = signing disabled. The
    # self-hosted operator owns this key; see SECURITY.md "Nostr key handling".
    # Deliberately NOT in _INSECURE_DEFAULTS: the feature is optional and an
    # empty value just disables it.
    nostr_seckey: str = ""

    # Logging
    log_level: str = "INFO"
    payout_reconcile_seconds: int = 20

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string (env-friendly) or a list."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("public_base_url")
    @classmethod
    def _normalize_public_base_url(cls, value: str) -> str:
        # Stored without a trailing slash so composed webhook URLs stay clean.
        return value.strip().rstrip("/")

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    def enforce_production_safety(self) -> None:
        """Fail fast if production is running with insecure defaults.

        Called at application startup. A no-op outside production so local dev,
        tests, and tooling (alembic, seed scripts) keep working unchanged.
        """
        if not self.is_production:
            return

        problems: list[str] = []
        for field, insecure in _INSECURE_DEFAULTS.items():
            if getattr(self, field) == insecure:
                problems.append(f"ORCHESTRATOR_{field.upper()} is still the default placeholder")

        if "*" in self.cors_origins:
            problems.append("ORCHESTRATOR_CORS_ORIGINS must not include '*' in production")
        if not self.cors_origins:
            problems.append("ORCHESTRATOR_CORS_ORIGINS must be set in production")

        # BTCPay must be able to deliver webhooks to this URL, so a local-only
        # host (the localhost default included) can never be right in production.
        public_host = (urlsplit(self.public_base_url).hostname or "").lower()
        if not public_host or public_host in _LOCAL_ONLY_HOSTNAMES:
            problems.append(
                "ORCHESTRATOR_PUBLIC_BASE_URL must be a publicly reachable URL "
                "(still the local-only default)"
            )

        if problems:
            raise RuntimeError(
                "Refusing to start in production with insecure configuration:\n  - "
                + "\n  - ".join(problems)
                + "\nSet the corresponding ORCHESTRATOR_* environment variables and retry."
            )


settings = Settings()
