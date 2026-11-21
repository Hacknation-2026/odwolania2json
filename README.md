# odwolania2json

Urząd Zamówień Publicznych – Odwołania2json (HackNation 2026).
Rozpoznaje dokumenty ze sprawy odwoławczej KIO (odwołanie, pełnomocnictwo, potwierdzenie przelewu) i zapisuje dla każdego PDF-a JSON w [modelu UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/main/oczekiwane-json). Dokumenty spoza tych klas dostają pusty plik `.json`.

**Pipeline (w całości lokalnie, CPU, bez API):** PDF → tekst (pypdfium2, OCR RapidOCR dla skanów) → naprawa polskich znaków po OCR → klasyfikacja typu (TF-IDF + regresja logistyczna, ~4 MB) → ekstrakcja pól regułami (wbudowane + konfigurowane w YAML) → dopasowanie do szablonu z YAML i normalizacja → JSON.

**Stack (tylko open source):** Python 3.13, pypdfium2, RapidOCR/ONNX Runtime, scikit-learn, FastAPI. Opcjonalnie LLM przez API zgodne z OpenAI – tylko dla nowych klas z YAML, które nie mają jeszcze reguł, i tylko gdy w `.env` ustawiono `LLM_API_KEY`.

Wynik na danych UZP (`dane/`, 226 PDF-ów): F1 0,978; dokumenty syntetyczne 0,997, prawdziwe skany (`dane/skany`) 0,85–0,86 (także na odłożonej części, nieużywanej przy pisaniu reguł), negatywy 16/16 odrzucone. Pomiar: `python backend/scripts/bench.py`. Dokumentacja techniczna: [docs/DOKUMENTACJA.md](docs/DOKUMENTACJA.md).

## Uruchomienie (Windows)

Nie trzeba instalować Pythona, mieć GPU ani niczego trenować – wytrenowane modele są w repo.

1. Pobierz repozytorium (`git clone` albo „Code → Download ZIP” i rozpakuj).
2. Wrzuć sprawy do folderu `input/`, np. `input/case1/*.pdf`.
3. Uruchom **`start.bat`** (dwuklik albo z wiersza poleceń). Wyniki pojawią się w `output/case1/<nazwa>.json`, ślad przetwarzania w `logs/`.

GUI: **`start_gui.bat`** – sam otwiera przeglądarkę (domyślnie http://localhost:8765; przy zajętym porcie kolejny wolny). Pliki wgrywa się przeciągnięciem, wynik można pobrać jako JSON.

**Pierwsze uruchomienie** potrzebuje internetu i trwa ok. 2–5 minut: `tools/setup.bat` tworzy środowisko `.venv` z Pythonem 3.13 i instaluje zależności. Jeśli na komputerze nie ma Pythona 3.13, pobiera [uv](https://github.com/astral-sh/uv) (open source), który instaluje Pythona do `tools/python/` – wewnątrz projektu, bez uprawnień administratora. Kolejne uruchomienia działają bez internetu i startują w kilka sekund. Całość zajmuje ok. 600 MB; usunięcie folderu projektu usuwa wszystko.

Każde uruchomienie najpierw czyści wyniki poprzednich z `output/`, więc po przebiegu `output/` odpowiada dokładnie PDF-om z `input/` (`start.bat --keep-output` wyłącza czyszczenie). `input/` nie jest zmieniany. Dokumenty spoza klas i nieczytelne PDF-y dostają pusty plik `.json`; jeden zły plik nie zatrzymuje reszty.

Czas na laptopie bez GPU: dokument z warstwą tekstową poniżej 1 s, skan ok. 2 s na stronę (OCR).

Opcjonalnie Docker: `docker compose up --build` (API na :8000, GUI na :8080).

## Struktura

- `backend/app/` – kod (CLI `app.cli`, API `app.main`, pipeline; reguły ekstrakcji w `extraction/rules.py`)
- `backend/config/classes/` – klasy dokumentów: nazwa, opis + szablon wyjściowego JSON-a
- `backend/config/dictionaries/` – słowniki (np. `czynnosc_powod`)
- `model/` – wytrenowany klasyfikator typu dokumentu (kod: `backend/app/text_model.py`, trening: `train.bat`)
- `model/src/augment.py` – generator „zeskanowanych” wersji PDF-ów do treningu (narzędzie deweloperskie, `pip install -r requirements-dev.txt`)
- `frontend/` – strona do wgrywania PDF-ów
- `input/`, `output/` – foldery wymagane przez UZP

## Nowa klasa dokumentu

Bez zmian w kodzie – szczegóły i opis wszystkich opcji: [docs/DOKUMENTACJA.md](docs/DOKUMENTACJA.md).
1. Dodaj plik YAML w `backend/config/classes/`: szablon wyjściowego JSON-a i reguły `extract:` przy polach (etykieta, data, kwota, rachunek, wyrażenie regularne, słowa kluczowe…). Gotowy wzór klasy skonfigurowanej wyłącznie w YAML: [ogloszenie_bzp.yaml](backend/config/examples/ogloszenie_bzp.yaml).
2. Wrzuć kilka przykładowych PDF-ów do `training/<nazwa klasy>/` (albo w układzie UZP: PDF + oczekiwany JSON obok). Inne dokumenty, które mają być odrzucane, do `training/brak/`.
3. Uruchom `train.bat` – trening trwa około minuty na CPU; przed zapisem modelu wypisuje wynik walidacji krzyżowej (całe sprawy odłożone).

Nowe pole w istniejącej klasie to też tylko wpis w YAML. Trzy klasy z zadania UZP używają dodatkowo wbudowanych reguł (`rules:` w YAML, `backend/app/extraction/rules.py`), bo dają najwyższe F1; część ich konfiguracji (np. wzorce powodów odwołania) też jest w YAML.

Klasyfikator patrzy na początek dokumentu (1. strona, kolejne gdy jest mało tekstu) i ignoruje polskie znaki, bo OCR często je gubi.

## Augmentacja danych treningowych (skany)

`model/src/augment.py` zamienia czyste PDF-y w realistyczne „skany” (zachowując pary PDF + JSON), żeby powiększyć zbiór treningowy: złe dopasowanie do strony (pomniejszenie z marginesem), jasność/kontrast i cienie, obrót i skos, szum, smugi, rozmycie, kompresja JPEG. Narzędzie deweloperskie – wymaga `pip install -r requirements-dev.txt`.

```bash
python model/src/augment.py --input-file model/data/raw/przyklad_01/odwolanie.pdf --output distorted.pdf --bad-fit
python model/src/augment.py --dataset-dir model/data/raw --output-dir model/data/raw_augmented --copies 2 --preset realistic
```

Wygenerowane sprawy (`model/data/raw_augmented/`, poza repo) można dodać do treningu klasyfikatora: `train.bat --data ../data/hacknation-2026/dane ../model/data/raw_augmented`.

## Testy i ewaluacja

```bash
git clone https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026 data/hacknation-2026
cd backend && ..\.venv\Scripts\python -m pytest
..\.venv\Scripts\python -m app.cli --input ../data/hacknation-2026/dane --output ../output/dane
..\.venv\Scripts\python scripts/evaluate.py --gold ../data/hacknation-2026/dane --pred ../output/dane
```
