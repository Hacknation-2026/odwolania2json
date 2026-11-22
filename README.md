# odwolania2json

Urząd Zamówień Publicznych – Odwołania2json (HackNation 2026).
Rozpoznaje dokumenty ze sprawy odwoławczej KIO (odwołanie, pełnomocnictwo, potwierdzenie przelewu) i zapisuje dla każdego PDF-a JSON w [modelu UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/main/oczekiwane-json). Dokumenty spoza tych klas dostają pusty plik `.json`.

**Pipeline (w całości lokalnie, CPU, bez API):** PDF → tekst (pypdfium2, OCR RapidOCR dla skanów) → naprawa polskich znaków po OCR → klasyfikacja typu (TF-IDF + regresja logistyczna, ~4 MB) → ekstrakcja pól regułami (wbudowane + konfigurowane w YAML) → dopasowanie do szablonu z YAML i normalizacja → JSON.

**Stack (tylko open source):** Python 3.13, pypdfium2, RapidOCR/ONNX Runtime, scikit-learn, FastAPI. Opcjonalnie LLM przez API zgodne z OpenAI – tylko dla nowych klas z YAML, które nie mają jeszcze reguł, i tylko gdy w `.env` ustawiono `LLM_API_KEY`.

Wynik na danych UZP (`dane/`, 226 PDF-ów): F1 0,978; dokumenty syntetyczne 0,997, prawdziwe skany (`dane/skany`) 0,85–0,86 (także na odłożonej części, nieużywanej przy pisaniu reguł), negatywy 16/16 odrzucone. Pomiar: `python backend/scripts/bench.py`. Raport z wynikami (macierze pomyłek, F1 per pole, postęp optymalizacji): [docs/wyniki.html](docs/wyniki.html). Dokumentacja techniczna: [docs/DOKUMENTACJA.md](docs/DOKUMENTACJA.md).

## Uruchomienie

Nie trzeba instalować Pythona, mieć GPU ani niczego trenować – wytrenowane modele są w repo. Ten sam projekt działa na Windows (`.bat`) i Linuksie/Ubuntu (`.sh`).

1. Pobierz repozytorium (`git clone` albo „Code → Download ZIP” i rozpakuj).
2. Wrzuć sprawy do folderu `input/`, np. `input/case1/*.pdf`.
3. Uruchom:
   - **Ubuntu / Linux:** `./start.sh` (z ZIP-a, jeśli prawa wykonywania się zgubiły: `bash start.sh`),
   - **Windows:** `start.bat` (dwuklik albo z wiersza poleceń).

   Wyniki pojawią się w `output/case1/<nazwa>.json`, ślad przetwarzania w `logs/`.

| | Windows | Ubuntu / Linux |
|---|---|---|
| przetwarzanie `input/` → `output/` | `start.bat` | `./start.sh` |
| GUI w przeglądarce | `start_gui.bat` | `./start_gui.sh` |
| trening klasyfikatora | `train.bat` | `./train.sh` |

GUI: **`start_gui.sh`** / **`start_gui.bat`** – otwiera przeglądarkę, jeśli jest (domyślnie http://localhost:8765; przy zajętym porcie kolejny wolny). Na maszynie wirtualnej, żeby otworzyć GUI z innego komputera: `GUI_HOST=0.0.0.0 ./start_gui.sh` i adres `http://<adres-maszyny>:8765`. Wgrywa się pliki PDF albo cały folder (przyciskiem lub przeciągnięciem; jak w CLI – PDF-y z folderu i jego podfolderów, jeden poziom w głąb). Przy każdym wyniku: porównanie PDF obok JSON-a, ślad przetwarzania, kopiowanie i pobranie JSON-a; „Pobierz wszystkie (.zip)” daje te same foldery i nazwy co `output/` w CLI. GUI nic nie zapisuje na dysku (nie używa `input/` ani `output/`).

**Pierwsze uruchomienie** potrzebuje internetu i trwa ok. 2–5 minut: `tools/setup.sh` (Linux) lub `tools/setup.bat` (Windows) tworzy środowisko `.venv` z Pythonem 3.13 i instaluje zależności. Jeśli w systemie nie ma Pythona 3.13 (np. Ubuntu 22.04/24.04 mają 3.10/3.12), pobiera [uv](https://github.com/astral-sh/uv) (open source), który instaluje Pythona do `tools/python/` – wewnątrz projektu, bez `sudo` i bez uprawnień administratora. Na Linuksie do pobrania wystarczy `curl`, `wget` albo systemowy `python3`; żadnych pakietów systemowych nie trzeba doinstalowywać. Kolejne uruchomienia działają bez internetu i startują w kilka sekund. Całość zajmuje ok. 600 MB; usunięcie folderu projektu usuwa wszystko.

Każde uruchomienie najpierw czyści wyniki poprzednich z `output/`, więc po przebiegu `output/` odpowiada dokładnie PDF-om z `input/` (`--keep-output` wyłącza czyszczenie; inne foldery: `./start.sh --input <folder> --output <folder>` lub to samo ze `start.bat` – ścieżki liczone od folderu projektu, folder podany w `--output` nie jest czyszczony). `input/` nie jest zmieniany. Dokumenty spoza klas i nieczytelne PDF-y dostają pusty plik `.json`; jeden zły plik nie zatrzymuje reszty.

Czas na laptopie bez GPU: dokument z warstwą tekstową poniżej 1 s, skan ok. 2–5 s na stronę (OCR; gęsto zapisane strony dłużej). OCR obejmuje tylko potrzebne strony: do klasyfikacji zwykle wystarcza pierwsza, a ze skanu odwołania czytane są 2 pierwsze strony (`max_ocr_pages` w YAML) – skan odwołania ok. 8–10 s (także przy 2 rdzeniach, jak na maszynie wirtualnej UZP).

Opcjonalnie Docker: `docker compose up --build` (API na :8000, GUI na :8080).

## Struktura

- `start.sh`/`.bat`, `start_gui.sh`/`.bat`, `train.sh`/`.bat` – uruchamianie (Linux/Windows); `tools/setup.sh`/`.bat` przygotowuje środowisko (`.venv`, w razie potrzeby Python w `tools/python/`)
- `backend/app/` – kod: CLI `app.cli`, API `app.main`, `pipeline.py`; `extraction/` – tekst i OCR (`pdf_text.py`, `ocr.py`), naprawa polskich znaków (`ocr_fix.py`), reguły wbudowane (`rules.py`) i silnik reguł z YAML (`engine.py`)
- `backend/config/classes/` – klasy dokumentów: szablon wyjściowego JSON-a i reguły ekstrakcji
- `backend/config/examples/` – przykładowa klasa skonfigurowana wyłącznie w YAML (`ogloszenie_bzp.yaml`)
- `backend/config/dictionaries/` – słowniki (np. `czynnosc_powod`); `backend/config/lexicon/` – słownik do naprawy polskich znaków po OCR
- `backend/scripts/` – `bench.py` (pomiar F1 na danych UZP), `evaluate.py`, `build_lexicon.py`
- `model/` – wytrenowany klasyfikator (`document_classifier.joblib`; kod: `backend/app/text_model.py`, trening: `train.sh`/`train.bat`) i model OCR (`ocr/`)
- `model/src/augment.py` – generator „zeskanowanych” wersji PDF-ów do treningu (narzędzie deweloperskie)
- `frontend/` – GUI bez frameworka i bez budowania: `index.html`, `css/styles.css`, moduły ES w `js/` (`app.js` – stan i kolejka, `api.js`, `render.js`, `folders.js`, `zip.js`, `util.js`)
- `docs/DOKUMENTACJA.md` – dokumentacja techniczna
- `input/`, `output/` – foldery wymagane przez UZP; `training/` (tworzony w razie potrzeby) – przykłady nowych klas do treningu

## Nowa klasa dokumentu

Bez zmian w kodzie – szczegóły i opis wszystkich opcji: [docs/DOKUMENTACJA.md](docs/DOKUMENTACJA.md).
1. Dodaj plik YAML w `backend/config/classes/`: szablon wyjściowego JSON-a i reguły `extract:` przy polach (etykieta, data, kwota, rachunek, wyrażenie regularne, słowa kluczowe…). Gotowy wzór klasy skonfigurowanej wyłącznie w YAML: [ogloszenie_bzp.yaml](backend/config/examples/ogloszenie_bzp.yaml).
2. Wrzuć kilka przykładowych PDF-ów do `training/<nazwa klasy>/` (albo w układzie UZP: PDF + oczekiwany JSON obok). Inne dokumenty, które mają być odrzucane, do `training/brak/`.
3. Uruchom `./train.sh` (Windows: `train.bat`) – trening trwa około minuty na CPU; przed zapisem modelu wypisuje wynik walidacji krzyżowej (całe sprawy odłożone).

Nowe pole w istniejącej klasie to też tylko wpis w YAML. Trzy klasy z zadania UZP używają dodatkowo wbudowanych reguł (`rules:` w YAML, `backend/app/extraction/rules.py`), bo dają najwyższe F1; część ich konfiguracji (np. wzorce powodów odwołania) też jest w YAML.

Klasyfikator patrzy na początek dokumentu (1. strona, kolejne gdy jest mało tekstu) i ignoruje polskie znaki, bo OCR często je gubi.

## Augmentacja danych treningowych (skany)

`model/src/augment.py` zamienia czyste PDF-y w realistyczne „skany” (zachowując pary PDF + JSON), żeby powiększyć zbiór treningowy: złe dopasowanie do strony (pomniejszenie z marginesem), jasność/kontrast i cienie, obrót i skos, szum, smugi, rozmycie, kompresja JPEG. Narzędzie deweloperskie – wymaga dodatkowych pakietów (PyMuPDF, Pillow). Z katalogu głównego:

```bat
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python model\src\augment.py --input-file model\data\raw\przyklad_01\odwolanie.pdf --output distorted.pdf --bad-fit
.venv\Scripts\python model\src\augment.py --dataset-dir model\data\raw --output-dir model\data\raw_augmented --copies 2 --preset realistic
```

Wygenerowane sprawy (`model/data/raw_augmented/`, poza repo) można dodać do treningu klasyfikatora: `./train.sh --data data/hacknation-2026/dane model/data/raw_augmented` (Windows: `train.bat` z tymi samymi argumentami; ścieżki względem folderu projektu).
aw_augmented`.

## Testy i ewaluacja

Dane UZP do testów i pomiarów (poza repo), z katalogu głównego (po pierwszym `start.sh`/`start.bat`, który tworzy `.venv`):

```bash
git clone https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026 data/hacknation-2026
cd backend
../.venv/bin/python -m pytest          # Windows: ..\.venv\Scripts\python -m pytest
../.venv/bin/python scripts/bench.py   # Windows: ..\.venv\Scripts\python scripts\bench.py
```

`bench.py` liczy F1 osobno dla dokumentów syntetycznych, negatywów i prawdziwych skanów (część robocza i odłożona); `--fields skany-dev` pokazuje błędy per pole, `--show skany/odwolania/0002/0002.pdf` – wynik obok wzorca. Tekst stron (z OCR) jest zapamiętywany w `data/cache/`, więc kolejne pomiary trwają kilkadziesiąt sekund. Ocena dowolnych wyników zapisanych przez CLI: `scripts\evaluate.py --gold <folder ze wzorcami> --pred <folder z wynikami>`.
