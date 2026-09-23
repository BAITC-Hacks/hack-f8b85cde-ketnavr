from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT_DIR / ".env")


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class Settings(BaseModel):
    data_zip_path: Path
    as_of_date: str
    max_recommendations: int = Field(ge=0)
    safety_stock_days: int
    iek_lead_time_days: int
    systeme_lead_time_days: int
    ai_provider: Literal["template", "openai", "nvidia", "auto"]
    ai_max_rows: int
    openai_api_key: str
    openai_model: str
    nvidia_api_key: str
    nvidia_model: str
    nvidia_base_url: str


@lru_cache
def get_settings() -> Settings:
    provider = os.getenv("AI_PROVIDER", "template").strip().lower()
    if provider not in {"template", "openai", "nvidia", "auto"}:
        provider = "template"
    return Settings(
        data_zip_path=Path(
            os.getenv(
                "DATA_ZIP_PATH",
                r"C:\Users\ulana\Downloads\Excel_IEK_Systeme_Electric_оформленные.zip",
            )
        ),
        as_of_date=os.getenv("AS_OF_DATE", "2026-09-22"),
        max_recommendations=_int("MAX_RECOMMENDATIONS", 0),
        safety_stock_days=_int("SAFETY_STOCK_DAYS", 14),
        iek_lead_time_days=_int("IEK_LEAD_TIME_DAYS", 18),
        systeme_lead_time_days=_int("SYSTEME_LEAD_TIME_DAYS", 14),
        ai_provider=provider,
        ai_max_rows=_int("AI_MAX_ROWS", 8),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        nvidia_api_key=os.getenv("NVIDIA_API_KEY", ""),
        nvidia_model=os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct"),
        nvidia_base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    )
