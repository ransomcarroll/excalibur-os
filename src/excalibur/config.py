from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    github_token: str
    linear_api_key: str
    linear_team_id: str
    linear_project_id: str | None = None
    github_repo: str
    excalibur_base_branch: str = "dev"
    excalibur_max_issues_per_shipment: int = 8
    excalibur_token_budget_per_group: int = 2_000_000
    excalibur_workdir: str = "/var/excalibur/workspaces"
    excalibur_executor_timeout_seconds: int = 60 * 60  # 1h per group
    slack_webhook_url: str | None = None

    model: str = Field(default="claude-opus-4-7", description="Model for grouper + executor")


def load() -> Settings:
    return Settings()  # type: ignore[call-arg]
