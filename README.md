# odwolania2json

Urząd Zamówień Publicznych – Odwołania2json (HackNation 2026).
Rozpoznaje dokumenty ze sprawy odwoławczej KIO (odwołanie, pełnomocnictwo, potwierdzenie przelewu) i zapisuje dla każdego PDF-a JSON w [modelu UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/main/oczekiwane-json). Dokumenty spoza tych klas dostają pusty plik `.json`.

**Pipeline (w całości lokalnie, CPU, bez API):** PDF → tekst (pypdfium2, OCR RapidOCR dla skanów) → klasyfikacja typu (TF-IDF + regresja logistyczna, ~4 MB) → ekstrakcja pól regułami (`backend/app/extraction/rules.py`) → dopasowanie do szablonu z YAML i normalizacja → JSON.

**Stack (tylko open source):** Python 3.13, pypdfium2, RapidOCR/ONNX Runtime, scikit-learn, FastAPI. Opcjonalnie LLM przez API zgodne z OpenAI – tylko dla nowych klas z YAML, które nie mają jeszcze reguł, i tylko gdy w `.env` ustawiono `LLM_API_KEY`.

Wynik na danych UZP (`dane/`, 226 PDF-ów): F1 0,938; dokumenty syntetyczne ~0,997, prawdziwe skany (`dane/skany`) 0,387. Czas: ok. 2 s na plik.

## Uruchomienie

Wytrenowany model jest w repo – nic nie trzeba trenować ani konfigurować.

1. Wrzuć sprawy do `input/` (np. `input/case1/*.pdf`).
2. Uruchom `start.bat` (tworzy `.venv` i instaluje zależności przy pierwszym uruchomieniu) – wyniki w `output/case1/<nazwa>.json`, ślad przetwarzania w `logs/`.

Każde uruchomienie najpierw czyści wyniki poprzednich z `output/`, więc po przebiegu `output/` odpowiada dokładnie PDF-om z `input/` (`--keep-output` wyłącza czyszczenie). `input/` nie jest zmieniany. Dokumenty spoza klas i nieczytelne PDF-y dostają pusty plik `.json`; jeden zły plik nie zatrzymuje reszty.

GUI: `start_gui.bat` – sam otwiera przeglądarkę (domyślnie http://localhost:8765, przy zajętym porcie kolejny wolny; Swagger: `/docs`). Opcjonalnie Docker: `docker compose up --build`.

## Struktura

- `backend/app/` – kod (CLI `app.cli`, API `app.main`, pipeline; reguły ekstrakcji w `extraction/rules.py`)
- `backend/config/classes/` – klasy dokumentów: nazwa, opis + szablon wyjściowego JSON-a
- `backend/config/dictionaries/` – słowniki (np. `czynnosc_powod`)
- `model/` – wytrenowany klasyfikator typu dokumentu (kod: `backend/app/text_model.py`, trening: `train.bat`)
- `model/src/augment.py` – generator „zeskanowanych” wersji PDF-ów do treningu (narzędzie deweloperskie, `pip install -r requirements-dev.txt`)
- `frontend/` – strona do wgrywania PDF-ów
- `input/`, `output/` – foldery wymagane przez UZP

## Nowa klasa dokumentu

Bez zmian w kodzie:
1. Dodaj plik YAML w `backend/config/classes/` (opis + szablon wyjściowego JSON-a). Wzór: [odwolanie.yaml](backend/config/classes/odwolanie.yaml).
2. Wrzuć kilka przykładowych PDF-ów do `training/<nazwa klasy>/` (albo w układzie UZP: PDF + oczekiwany JSON obok). Inne dokumenty, które mają być odrzucane, do `training/brak/`.
3. Uruchom `train.bat` – trening trwa około minuty na CPU; przed zapisem modelu wypisuje wynik walidacji krzyżowej (całe sprawy odłożone).

Pola nowej klasy wypełniają reguły zarejestrowane w `backend/app/extractor.py` (`RULES`). Dopóki klasa ich nie ma, dostaje szablon z wartościami `null` – albo, jeśli w `.env` ustawiono `LLM_API_KEY`, pola wyciąga LLM według opisów z YAML.

Klasyfikator patrzy na początek dokumentu (1. strona, kolejne gdy jest mało tekstu) i ignoruje polskie znaki, bo OCR często je gubi.

## Testy i ewaluacja

```bash
git clone https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026 data/hacknation-2026
cd backend && ..\.venv\Scripts\python -m pytest
..\.venv\Scripts\python -m app.cli --input ../data/hacknation-2026/dane --output ../output/dane
..\.venv\Scripts\python scripts/evaluate.py --gold ../data/hacknation-2026/dane --pred ../output/dane
```
