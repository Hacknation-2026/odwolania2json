from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT_DIR / ".env",), extra="ignore")

    # LLM: dowolne API zgodne z OpenAI. OpenRouter to placeholder na czas developmentu -
    # do zgłoszenia wymagany dostawca z serwerami w UE/EOG i model open-weight.
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "google/gemma-4-31b-it:free"  # na OpenRouter tylko modele ":free"
    llm_temperature: float = 0.0
    llm_structured_output: bool = True
    llm_max_retries: int = 5

    # Klasyfikacja
    classify_pages: int = 2
    classify_max_chars: int = 5000
    min_confidence: float = 0.5

    # Ekstrakcja tekstu
    ocr_enabled: bool = True
    ocr_min_chars: int = 50  # poniżej tej liczby znaków strona traktowana jako skan

    gui_port: int = 8765  # first port tried by start_gui.bat; next free one is used if taken

    config_dir: Path = BACKEND_DIR / "config"
    frontend_dir: Path = ROOT_DIR / "frontend"
    input_dir: Path = ROOT_DIR / "input"
    output_dir: Path = ROOT_DIR / "output"
    trace_dir: Path = ROOT_DIR / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
