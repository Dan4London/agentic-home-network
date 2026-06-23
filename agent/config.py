from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    probe_host: str = "192.168.1.70"
    probe_user: str = "pi"
    probe_password: str = ""
    probe_ssh_key: str = ""
    latency_targets: str = "192.168.1.1,1.1.1.1,8.8.8.8"
    use_mock_probes: bool = False
    dry_run: bool = True

    @property
    def targets(self) -> list[str]:
        return [t.strip() for t in self.latency_targets.split(",") if t.strip()]

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key.strip())


settings = Settings()
