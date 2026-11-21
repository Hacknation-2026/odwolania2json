# odwolania2json

Urząd Zamówień Publicznych – Odwołania2json (HackNation 2026).
Rozpoznaje dokumenty ze sprawy odwoławczej KIO (odwołanie, pełnomocnictwo, potwierdzenie przelewu) i zapisuje dla każdego PDF-a JSON w [modelu UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/main/oczekiwane-json). Dokumenty spoza tych klas dostają pusty plik `.json`.

**Pipeline:** PDF → tekst (pypdfium2, OCR RapidOCR dla skanów) → klasyfikacja typu (lokalny model TF-IDF + regresja logistyczna, CPU, ~4 MB) → ekstrakcja pól wg szablonu z YAML (LLM + JSON Schema) → normalizacja → JSON. Klasyfikacja działa w pełni lokalnie; dokumenty odrzucone przez klasyfikator nie trafiają do LLM.

**Stack (tylko open source):** Python 3.13, pypdfium2, RapidOCR/ONNX Runtime (CPU), scikit-learn, FastAPI, model open-weight przez API zgodne z OpenAI – tymczasowo OpenRouter z darmowym modelem (placeholder; docelowo dostawca z serwerami w UE/EOG, model do wyboru).

## Uruchomienie

1. Skopiuj `.env.example` do `.env` i wpisz `LLM_API_KEY`.
2. Wrzuć sprawy do `input/` (np. `input/case1/*.pdf`).
3. Uruchom `start.bat` – wyniki w `output/case1/<nazwa>.json`, ślad przetwarzania w `logs/`.

GUI: `start_gui.bat` – sam otwiera przeglądarkę (domyślnie http://localhost:8765, przy zajętym porcie kolejny wolny; Swagger: `/docs`). Opcjonalnie Docker: `docker compose up --build`.

## Struktura

- `backend/app/` – kod (CLI `app.cli`, API `app.main`, pipeline)
- `backend/config/classes/` – klasy dokumentów: nazwa, opis + szablon wyjściowego JSON-a
- `backend/config/dictionaries/` – słowniki (np. `czynnosc_powod`)
- `model/` – wytrenowany klasyfikator typu dokumentu (kod: `backend/app/text_model.py`, trening: `train.bat`)
- `frontend/` – strona do wgrywania PDF-ów
- `input/`, `output/` – foldery wymagane przez UZP

## Nowa klasa dokumentu

Bez zmian w kodzie:
1. Dodaj plik YAML w `backend/config/classes/` (opis + szablon wyjściowego JSON-a). Wzór: [odwolanie.yaml](backend/config/classes/odwolanie.yaml).
2. Wrzuć kilka przykładowych PDF-ów do `training/<nazwa klasy>/` (albo w układzie UZP: PDF + oczekiwany JSON obok). Inne dokumenty, które mają być odrzucane, do `training/brak/`.
3. Uruchom `train.bat` – trening trwa około minuty na CPU; przed zapisem modelu wypisuje wynik walidacji krzyżowej (całe sprawy odłożone).

Klasyfikator patrzy na początek dokumentu (1. strona, kolejne gdy jest mało tekstu) i ignoruje polskie znaki, bo OCR często je gubi.

## Testy i ewaluacja

```bash
git clone https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026 data/hacknation-2026
cd backend && ..\.venv\Scripts\python -m pytest
..\.venv\Scripts\python -m app.cli --input ../data/hacknation-2026/dane --output ../output/dane
..\.venv\Scripts\python scripts/evaluate.py --gold ../data/hacknation-2026/dane --pred ../output/dane
```
