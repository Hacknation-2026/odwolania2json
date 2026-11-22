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

    # Klasyfikacja: lokalny model (app/text_model.py), trenowany przez train.bat
    classifier_model_path: Path = ROOT_DIR / "model" / "document_classifier.joblib"
    classify_min_chars: int = 1000  # model widzi 1. stronę, kolejne tylko gdy tekstu jest mniej
    classify_max_pages: int = 3
    min_confidence: float = 0.5  # poniżej tej pewności dokument trafia do "brak" (pusty JSON)
    training_data_dirs: list[Path] = [ROOT_DIR / "data" / "hacknation-2026" / "dane", ROOT_DIR / "training"]

    # Ekstrakcja tekstu
    ocr_enabled: bool = True
    ocr_min_chars: int = 50  # poniżej tej liczby znaków strona traktowana jako skan
    ocr_dpi: int = 200  # rozdzielczość renderowania strony do OCR (300 dpi nie poprawia wyników)
    # linie tekstu rozpoznawane pojedynczo: ~2x szybciej niż paczkami po 6 przy prawie tej samej jakości
    # (limit UZP: 150 PDF-ów w 45 min na laptopie bez GPU)
    ocr_rec_batch: int = 1
    ocr_threads: int = -1  # wątki OCR (env OCR_THREADS); -1 = automatycznie (app/extraction/ocr.py: _threads)
    # model rozpoznawania pisma łacińskiego (PP-OCRv5, Apache-2.0) dołączony do repo - bez pobierania przy pierwszym skanie
    ocr_rec_model_path: Path = ROOT_DIR / "model" / "ocr" / "latin_PP-OCRv5_rec_mobile.onnx"

    gui_port: int = 8765  # first port tried by start_gui.bat/.sh; next free one is used if taken
    # 127.0.0.1 = GUI only on this computer; GUI_HOST=0.0.0.0 opens it to the network (e.g. a VM)
    gui_host: str = "127.0.0.1"

    config_dir: Path = BACKEND_DIR / "config"
    frontend_dir: Path = ROOT_DIR / "frontend"
    input_dir: Path = ROOT_DIR / "input"
    output_dir: Path = ROOT_DIR / "output"
    trace_dir: Path = ROOT_DIR / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
