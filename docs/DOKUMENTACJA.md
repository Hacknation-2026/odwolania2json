# Odwołania2json – dokumentacja techniczna

Spis treści:
1. [Architektura](#1-architektura)
2. [Konfiguracja klasy dokumentu (YAML)](#2-konfiguracja-klasy-dokumentu-yaml)
3. [Dodanie nowej klasy dokumentu](#3-dodanie-nowej-klasy-dokumentu)
4. [Dodanie pola do istniejącej klasy](#4-dodanie-pola-do-istniejącej-klasy)
5. [Transparentność](#5-transparentność)
6. [Jakość i wydajność](#6-jakość-i-wydajność)

## 1. Architektura

Całość działa lokalnie na CPU – bez API, bez GPU, bez klucza i bez trenowania przed pierwszym uruchomieniem (wytrenowany klasyfikator jest w repozytorium).

```
PDF
 │
 ├─ 1. Tekst            pypdfium2 (warstwa tekstowa) / RapidOCR (skany, strona < 50 znaków)
 │                      app/extraction/pdf_text.py, ocr.py
 ├─ 2. Naprawa OCR      przywracanie polskich znaków ze słownika, "Sp. z 0.o.", "N1P"...
 │                      app/extraction/ocr_fix.py, config/lexicon/slowa.txt
 ├─ 3. Klasyfikacja     TF-IDF (słowa + n-gramy znaków) + regresja logistyczna, ~4 MB;
 │                      klasa "brak" uczona na dokumentach negatywnych -> pusty .json
 │                      app/classifier.py, app/text_model.py, model/document_classifier.joblib
 ├─ 4. Ekstrakcja       a) reguły wbudowane klasy (`rules:` w YAML)       app/extraction/rules.py
 │                      b) reguły z YAML (`extract:` przy polach)          app/extraction/engine.py
 │                      c) opcjonalnie LLM - tylko gdy ustawiono LLM_API_KEY
 └─ 5. Dopasowanie      wynik zawsze ma dokładnie kształt szablonu z YAML; normalizacja
                        (NIP, KRS, BZP, TED, daty, kwoty), pola wyliczane ze słowników
                        app/schema.py, app/normalizers.py
 │
JSON  (+ ślad przetwarzania w logs/)
```

| Moduł | Rola |
|---|---|
| `backend/app/cli.py` | CLI: `input/` → `output/` (to samo drzewo i nazwy), uruchamiane przez `start.bat` |
| `backend/app/main.py`, `gui.py`, `frontend/` | API (FastAPI) i GUI w przeglądarce (`start_gui.bat`) |
| `backend/app/pipeline.py` | spina kroki 1–5; OCR tylko dla stron, które są potrzebne |
| `backend/config/classes/*.yaml` | **klasy dokumentów** – jedyne miejsce, które trzeba zmienić przy rozbudowie |
| `backend/config/dictionaries/*.yaml` | słowniki (np. powody odwołania) |
| `backend/app/train_classifier.py` | trening klasyfikatora z klas w YAML (`train.bat`) |
| `backend/scripts/bench.py` | pomiar F1 na danych UZP (syntetyczne, negatywy, prawdziwe skany) |

Wszystkie zależności są open source (licencje w `requirements.txt`).

## 2. Konfiguracja klasy dokumentu (YAML)

Każda klasa to jeden plik w `backend/config/classes/`:

```yaml
name: przelew                     # nazwa klasy (folder z przykładami treningowymi: training/przelew/)
label: Potwierdzenie przelewu     # nazwa wyświetlana w GUI
description: >                    # opis (GUI, opcjonalny LLM)
  Potwierdzenie wykonania przelewu bankowego...
max_pages: 1                      # ile pierwszych stron czytać przy ekstrakcji
rules: przelew                    # opcjonalnie: wbudowane reguły Pythona dla tej klasy
output:                           # SZABLON wynikowego JSON-a - dokładnie taki kształt dostaje plik
  przelew_bankowy:
    kwota: {type: number, description: "Kwota przelewu"}
    na_rachunek: {type: string, normalize: digits, description: "Rachunek odbiorcy"}
```

### Szablon `output`

- **obiekt** – mapa `nazwa: węzeł`,
- **tablica** – lista z jednym elementem (szablon elementu), np. `Odwolujacy: [ {...} ]`,
- **pole (liść)** – mapa z kluczem `type`:

| Klucz | Znaczenie |
|---|---|
| `type` | `string`, `integer`, `number`, `date` (zawsze `RRRR-MM-DD`) |
| `description` | opis pola |
| `normalize` | `digits` (same cyfry), `krs` (10 cyfr), `bzp` (`2026/BZP00123456/01`), `ted` (`123456-2026`) |
| `enum` | dozwolone wartości, np. `[0, 1]` – inne zamieniane na `null` |
| `dictionary` | wartość musi być kluczem słownika z `config/dictionaries/` |
| `derive` | pole wyliczane ze słownika, np. `{from: czynnosc_powod_id, dictionary: czynnosc_powod}` |
| `extract` | reguła ekstrakcji z YAML (poniżej) |
| `keywords` | wzorce dla reguł wbudowanych (np. powód odwołania w `odwolanie.yaml`) |

### Reguły ekstrakcji `extract:`

Etykiety, słowa kluczowe i wzorce są dopasowywane **bez względu na wielkość liter i polskie znaki** (działa też na tekście z OCR); wartość jest brana z oryginalnego tekstu.

```yaml
numer_ogloszenia:
  type: string
  extract: {after: ['Numer ogłoszenia\s*:'], value: line}
```

| Klucz | Znaczenie |
|---|---|
| `after` | lista etykiet (wyrażenia regularne); wartość jest czytana zaraz za pierwszą znalezioną |
| `value` | co odczytać: `line` (reszta linii albo następna niepusta), `text` (kilka linii), `date`, `amount`, `account` (26 cyfr), `digits`, `email`, `person` (imię i nazwisko), `word`, `flag` (1 gdy etykieta jest w tekście) |
| `pattern` | własne wyrażenie regularne z jedną grupą (zamiast `value`) |
| `until`, `lines` | dla `value: text`: etykiety kończące wartość / maks. liczba linii |
| `length` | dla `value: digits`: wymagana liczba cyfr, np. `10` albo `[9, 14]` |
| `keywords` | lista `{id, pattern}` – wynikiem jest `id` pierwszego pasującego wzorca (np. pole słownikowe) |
| `default` | wartość, gdy nic nie znaleziono (np. `0` dla `flag`) |
| `override` | `true` – wartość z YAML zastępuje wynik reguł wbudowanych (domyślnie tylko uzupełnia puste pola) |

Zawężanie tekstu dla grupy pól:

```yaml
zamawiajacy:
  _section: {from: ['SEKCJA I\b'], to: ['SEKCJA II\b']}   # pola poniżej widzą tylko ten fragment
  nazwa: {type: string, extract: {after: ['Nazwa zamawiającego\s*:'], value: line}}
strony:
  - _split: '^\d+\)'          # tablica: jeden element na każdy blok zaczynający się od "1)", "2)"...
    nazwa: {type: string, extract: {pattern: '^\d+\)\s*(.+)$'}}
```

Pełny, działający przykład: [`backend/config/examples/ogloszenie_bzp.yaml`](../backend/config/examples/ogloszenie_bzp.yaml).

### Reguły wbudowane (`rules:`)

Dla trzech klas z zadania UZP (`odwolanie`, `pelnomocnictwo`, `przelew`) najlepsze F1 dają ręcznie napisane reguły w `app/extraction/rules.py` (układy sekcji, konsorcja, kilku zamawiających, formularze banków). Klasa wskazuje je kluczem `rules:`, a pola z `extract:` mogą je uzupełniać. Część ich konfiguracji też jest w YAML – np. wzorce powodów odwołania (`keywords` przy `czynnosc_powod_id` w `odwolanie.yaml`).

## 3. Dodanie nowej klasy dokumentu

Bez zmian w kodzie:

1. **Plik klasy** – utwórz `backend/config/classes/<nazwa>.yaml` z `output` i regułami `extract:` (wzór: `config/examples/ogloszenie_bzp.yaml`; można go po prostu skopiować).
2. **Przykłady** – wrzuć kilka PDF-ów do `training/<nazwa>/`. Dokumenty, które mają być odrzucane, do `training/brak/`. Alternatywnie układ UZP: PDF + oczekiwany JSON obok (klasa rozpoznawana po kluczach JSON-a).
3. **Trening** – uruchom `train.bat` (ok. minuty na CPU). Przed zapisem modelu wypisuje wynik walidacji krzyżowej z odłożonymi całymi sprawami.
4. **Sprawdzenie** – wrzuć przykład do GUI (`start_gui.bat`) i obejrzyj „Ślad przetwarzania” albo uruchom `start.bat`.

Bez reguł `extract:` nowa klasa dostaje szablon z wartościami `null` (a jeśli w `.env` ustawiono `LLM_API_KEY` – pola wypełnia LLM według opisów z YAML).

## 4. Dodanie pola do istniejącej klasy

Dopisz pole z regułą `extract:` do szablonu w YAML – reguły wbudowane zostają, a nowe pole wypełni silnik YAML:

```yaml
# config/classes/przelew.yaml
output:
  przelew_bankowy:
    ...
    waluta: {type: string, enum: [PLN, EUR], extract: {pattern: '\d[\d\s]*[.,]\d{2}\s*(PLN|EUR)\b'}}
```

Zmiana słownika (np. nowy powód odwołania) = nowa pozycja w `config/dictionaries/czynnosc_powod.yaml` i wzorzec w `keywords` przy `czynnosc_powod_id`.

## 5. Transparentność

- **Ślad przetwarzania** dla każdego pliku (`logs/<sprawa>/<plik>.trace.json`, w GUI „Ślad przetwarzania”): klasa i pewność, prawdopodobieństwa wszystkich klas, najbardziej podobny przykład treningowy, źródło tekstu każdej strony (`text`/`ocr`), metoda ekstrakcji (`rules`, `yaml`, `llm`) i surowy wynik przed normalizacją, czas.
- Reguły są czytelnym kodem/YAML – każdą wartość da się prześledzić do etykiety w dokumencie.
- Wyniki pomiarów są odtwarzalne: `python scripts/bench.py` (z `backend/`).

## 6. Jakość i wydajność

Pomiar na danych UZP (`dane/`, 226 PDF-ów), F1 na poziomie pól (`backend/scripts/bench.py`):

| Część | Pliki | F1 |
|---|---|---|
| dokumenty syntetyczne | 180 | 0,997 |
| negatywy (mają dać pusty JSON) | 16 | 16/16 odrzuconych |
| prawdziwe skany – część robocza | 21 | 0,847 |
| prawdziwe skany – **odłożone** (nieużywane przy pisaniu reguł) | 9 | **0,859** |
| razem | 226 | 0,978 |

Skany są podzielone na stałe: reguły były rozwijane tylko na części roboczej, odłożona część (`0003`, `0006`, `0009` każdego typu) przybliża wynik na ukrytym zbiorze testowym. Słownik do naprawy OCR jest budowany wyłącznie z dokumentów z warstwą tekstową, nigdy ze skanów.

Wydajność (laptop, CPU, bez GPU): dokument z warstwą tekstową < 0,5 s, skan ok. 2 s na stronę OCR; pełny zbiór UZP (226 plików) ok. 4 minuty – z dużym zapasem względem limitu 150 plików / 45 minut.
