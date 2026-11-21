from __future__ import annotations

import re
from datetime import date
from typing import Any


_MONTHS = {
    "stycznia": 1,
    "styczeń": 1,
    "lutego": 2,
    "luty": 2,
    "marca": 3,
    "marzec": 3,
    "kwietnia": 4,
    "kwiecień": 4,
    "maja": 5,
    "maj": 5,
    "czerwca": 6,
    "czerwiec": 6,
    "lipca": 7,
    "lipiec": 7,
    "sierpnia": 8,
    "sierpień": 8,
    "września": 9,
    "wrzesień": 9,
    "października": 10,
    "październik": 10,
    "listopada": 11,
    "listopad": 11,
    "grudnia": 12,
    "grudzień": 12,
}
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_PATTERN = (
    rf"(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{4}}|"
    rf"\d{{1,2}}\s+(?:{_MONTH_PATTERN})\s+\d{{4}})"
)
_PERSON_WORD = r"[^\W\d_]+(?:[-'’][^\W\d_]+)*"
_PERSON_NAME_PATTERN = rf"{_PERSON_WORD}(?:\s+{_PERSON_WORD}){{1,2}}"
_EMAIL_PATTERN = r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"
_REASON_DESCRIPTIONS = {
    1: "Decyzja o odrzuceniu oferty",
    2: "Ogłoszenie wyboru oferty",
    3: "Decyzja o wykluczeniu wykonawcy",
    4: "Publikacja specyfikacji warunków zamówienia (SWZ)",
    5: "Modyfikacja treści SWZ",
    6: "Odpowiedzi/wyjaśnienia do SWZ",
    7: "Zaniechanie odrzucenia oferty",
    8: "Zaniechanie wykluczenia wykonawcy",
    9: "Decyzja o unieważnieniu postępowania",
    10: "Zaniechanie unieważnienia postępowania",
    11: "Opis przedmiotu zamówienia (OPZ)",
}
_LAWYER_PATTERN = re.compile(
    rf"\b(?:r\.\s*pr\.|adw\.|radca\s+prawny|adwokat)\s+"
    rf"(?P<name>{_PERSON_NAME_PATTERN}?)"
    r"(?=\s*(?:\(|,|;|\r?\n|$|\bnr\s+wpisu\b|\bdo\b|\badres\b))",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    return text.replace("\u00ad", "").replace("\xa0", " ")


def _lines(text: str) -> list[str]:
    return [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in _clean_text(text).splitlines()
    ]


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", _clean_text(text)).strip()


def _parse_date(value: str) -> str | None:
    value = value.strip().rstrip(".,;")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value).isoformat()
        numeric = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", value)
        if numeric:
            return date(
                int(numeric.group(3)),
                int(numeric.group(2)),
                int(numeric.group(1)),
            ).isoformat()
        polish = re.fullmatch(
            rf"(\d{{1,2}})\s+({_MONTH_PATTERN})\s+(\d{{4}})",
            value,
            re.IGNORECASE,
        )
        if polish:
            return date(
                int(polish.group(3)),
                _MONTHS[polish.group(2).lower()],
                int(polish.group(1)),
            ).isoformat()
    except ValueError:
        return None
    return None


def _header_date_and_place(text: str) -> tuple[str | None, str | None]:
    place_pattern = re.compile(
        r"^[A-ZĄĆĘŁŃÓŚŹŻ][\w’'-]*"
        r"(?:[ \t]+[A-ZĄĆĘŁŃÓŚŹŻ][\w’'-]*){0,3}$"
    )
    for line in _lines(text)[:70]:
        for match in re.finditer(_DATE_PATTERN, line, re.IGNORECASE):
            parsed = _parse_date(match.group())
            prefix = line[: match.start()]
            prefix = re.sub(r"\bdnia\s*$", "", prefix, flags=re.IGNORECASE)
            place = prefix.strip(" ,:-")
            if parsed and place_pattern.fullmatch(place):
                return parsed, place
    return None, None


def _first_action(text: str) -> str:
    action_list = re.search(r"(?i)\bpolegając\w*\s+na\s*:\s*", text) or re.search(
        r"(?i)\bodwołani\w*\s+(?:wobec|od)\s*:\s*", text  # "wnoszę odwołanie wobec: 1. ..."
    )
    if action_list:
        tail = text[action_list.end() :]
        first_item = re.search(r"(?:^|\s)1[.)]\s*", tail[:1500])
        if first_item:
            start = first_item.end()
            next_item = re.search(r"(?:;|\n)\s*2[.)]\s", tail[start:])
            end = start + next_item.start() if next_item else min(len(tail), start + 900)
            return _flat(tail[start:end]).strip(" ;")

    action = re.search(
        rf"(?is)\bZamawiając\w*\b.{{0,80}}?"
        rf"\b(?:w\s+dniu|dnia)\s*{_DATE_PATTERN}.{{0,250}}",
        text[:16000],
    )
    if not action:
        return ""
    sentence = action.group()
    parsed_date = re.search(_DATE_PATTERN, sentence, re.IGNORECASE)
    if parsed_date:
        boundary = re.search(
            r"[.!?](?=\s+[A-ZĄĆĘŁŃÓŚŹŻ])",
            sentence[parsed_date.end() :],
        )
        if boundary:
            sentence = sentence[: parsed_date.end() + boundary.start() + 1]
    return _flat(sentence)


def _first_allegation(text: str) -> str:
    match = re.search(r"(?im)^\s*Zarzut\s+nr\s*1\b", text)
    if not match:
        return ""
    tail = text[match.end() :]
    end = re.search(
        r"(?im)^\s*(?:Zarzut\s+nr\s*2\b|Wnoszę\s+o\s*:?)",
        tail,
    )
    return _flat(tail[: end.start()] if end else tail[:3000])


def _reason_id(text: str) -> int | None:
    def find_reason(segment: str) -> int | None:
        checks = (
            (7, r"\b(?:nie\s+odrzucił|zaniecha\w*\s+odrzucenia)\b"),
            (8, r"\b(?:nie\s+wykluczył|zaniecha\w*\s+wykluczenia)\b"),
            (10, r"\b(?:zaniecha\w*\s+unieważnienia|nie\s+unieważnił)\b"),
            (9, r"\bunieważni\w*\s+(?:postępowan|przetarg)"),
            (
                5,
                r"\b(?:zmodyfik\w*|modyfikac\w*)\b.{0,100}"
                r"\b(?:SWZ|Specyfikacji\s+Warunków\s+Zamówienia)\b",
            ),
            (
                6,
                r"\b(?:udziel\w*|odpowiedzi|wyjaśnieni\w*)\b.{0,120}"
                r"\b(?:odpowiedzi|wyjaśnieni\w*)\b",
            ),
            (12, r"\b(?:projektowan\w*\s+postanowie\w*\s+umowy|PPU)\b"),
            (11, r"\b(?:opis\w*\s+przedmiotu\s+zamówienia|OPZ)\b"),
            (3, r"\b(?:wyklucz\w*)\b"),
            (1, r"\b(?:odrzuc\w*\s+ofert\w*)\b"),
            (
                2,
                r"\b(?:ogłosił\s+wybór|wybór\s+oferty|wyboru\s+oferty|"
                r"wyborze\s+oferty|wyborze\s+jako)\b",
            ),
            (
                4,
                r"\b(?:opublikow\w*|publikacj\w*|ustaleni\w*)\b.{0,150}"
                r"\b(?:specyfikacj\w*|SWZ|ogłoszenie o zamówieniu)\b",
            ),
            (
                4,  # "treści Specyfikacji Warunków Zamówienia opublikowanej ..."
                r"\b(?:specyfikacj\w*\s+warunków\s+zamówienia|SWZ)\b.{0,150}\bopublikow\w*",
            ),
        )
        for reason_id, pattern in checks:
            if re.search(pattern, segment, re.IGNORECASE):
                return reason_id
        return None

    action_reason = find_reason(_first_action(text))
    if action_reason is not None:
        return action_reason
    return find_reason(_first_allegation(text))


def _appeal_sections(text: str) -> dict[str, str]:
    starts = []
    offset = 0
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        match = re.match(r"(?i)^\s*(Odwołujący|Zamawiający)\b", line)
        if match:
            colon = line.find(":", match.end())
            heading_end = offset + (colon + 1 if colon >= 0 else len(line))
            valid = colon >= 0
            if not valid and "(" in line:
                for continuation in lines[index + 1 : index + 4]:
                    heading_end += len(continuation)
                    if ":" in continuation:
                        valid = True
                        break
                    if not continuation.strip():
                        break
            if valid:
                role = match.group(1).lower()
                previous = starts[-1] if starts else None
                if previous and previous[0] == role and not text[previous[2] : offset].strip(" '\"\n\t:"):
                    # "Zamawiający:" directly followed by "Zamawiający wspólnie udzielający zamówienia:"
                    starts[-1] = (role, previous[1], heading_end)
                else:
                    starts.append((role, offset, heading_end))
        offset += len(line)

    sections: dict[str, str] = {}
    for index, (role, start, heading_end) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        if role == "zamawiający":
            other_end = re.search(
                r"(?im)^\s*(?:dotyczy\s*:|odwołanie\b|wartość zamówienia\b)",
                text[heading_end:end],
            )
            if other_end:
                end = heading_end + other_end.start()
        if role not in sections:
            sections[role] = text[heading_end:end]
    return sections


def _entity_blocks(section: str, role: str) -> list[tuple[str, str]]:
    marker = re.compile(
        rf"(?im)^\s*\d+\)\s*(?:{re.escape(role)}\b|"
        r"(?:Lider|Partner)\s+Konsorcjum\b)\s*(?:[–-]\s*[^:\n]*)?:?"
    )
    markers = list(marker.finditer(section))
    if not markers and role == "Zamawiający":  # joint buyers: "1) Zarząd Dróg ...", "2) Zakład ..."
        markers = list(re.finditer(r"(?m)^\s*\d+\)\s+", section))
    if not markers or (not marker.search(section) and len(markers) < 2):
        return [("", section)]
    blocks = []
    for index, match in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(section)
        blocks.append((match.group(), section[match.end() : end]))
    return blocks


def _entity_name(block: str) -> str | None:
    skip = re.compile(
        r"^(?:ul\.|al\.|pl\.|krs\b|nip\b|regon\b|tel\.|e-?mail\b|"
        r"reprezentowan\w*\b|adres do korespondencji\b|"
        r"kontakt\b|zamawiający\b|odwołujący\b|lider konsorcjum\b|"
        r"partner konsorcjum\b|oraz\b|dalej\b|konsorcjum\b[^:]*:\s*$)",
        re.IGNORECASE,
    )
    lines = _lines(block)
    for index, line in enumerate(lines):
        line = re.sub(r"^\d+\)\s*", "", line)
        line = re.sub(r"\s*\((?:Lider|Partner)\s+Konsorcjum\)\s*$", "", line, flags=re.I)
        # "Jan Kowalski prowadzący działalność gospodarczą pod firmą" + next line = firm name
        if index + 1 < len(lines) and re.search(
            r"(?i)\bprowadząc\w*\s+działalno\w*.*\bpod\s+firm\w*\s*:?\s*$", line
        ):
            return lines[index + 1].strip(" ,;:")
        line = re.sub(r"^(?:Zamawiający|Odwołujący)\s*[–-]\s*(?:Lider|Partner)[^:]*:\s*", "", line, flags=re.I)
        if not line or skip.search(line):
            continue
        if re.match(r"^(?:Zamawiający|Odwołujący)\b", line, re.IGNORECASE):
            continue
        return line.strip(" ,;:")
    return None


def _registry(block: str, check_sole_proprietor: bool = True) -> dict[str, str | None]:
    result: dict[str, str | None] = {"krs": None, "nip": None, "regon": None}
    is_sole_proprietor = check_sole_proprietor and bool(
        re.search(r"\b(?:CEIDG|przedsiębiorc\w*)\b", block, re.IGNORECASE)
    )
    for key, digits in (("krs", 10), ("nip", 10), ("regon", (9, 14))):
        if key == "krs" and is_sole_proprietor:
            continue
        lengths = digits if isinstance(digits, tuple) else (digits,)
        # numbers may be split by spaces or dashes ("NIP: 999-509-02-81")
        match = re.search(rf"\b{key}\s*:?\s*(\d[\d \-]{{7,20}}\d)", block, re.IGNORECASE)
        if match:
            value = re.sub(r"\D", "", match.group(1))
            if len(value) in lengths:
                result[key] = value
    return result


def _lawyers(text: str) -> list[str]:
    names = []
    for match in _LAWYER_PATTERN.finditer(text):
        name = _flat(match.group("name")).strip(" ,.;:")
        if name not in names:
            names.append(name)
    return names


def _correspondence_firm(block: str) -> str | None:
    match = re.search(
        r"adres\s+do\s+korespondenc\w*\s*:\s*(.+?)"
        r"(?=,?\s+(?:ul\.|al\.|pl\.)\s|,?\s+(?:tel\.|e-?mail\b)|,\s*(?:ul\.|al\.|pl\.|tel\.|e-?mail)|$)",
        _flat(block),
        re.IGNORECASE,
    )
    return _flat(match.group(1)).strip(" ,") if match else None


def _letterhead_firm(text: str) -> str | None:
    """First 'Kancelaria ...' line of the letterhead or footer (not all caps, no web/e-mail)."""
    for line in _lines(text):
        if re.match(r"^Kancelari\w*\s+\S", line) and not line.isupper() and not re.search(r"@|www\.|\.example", line):
            return re.split(r"\s+(?:ul\.|al\.|pl\.|tel\.)\s", line)[0].strip(" ,;:")
    return None


def _appeal_entities(section: str, role: str) -> list[tuple[str, str, str | None]]:
    blocks = _entity_blocks(section, role)
    entities = []
    for marker, block in blocks:
        name = _entity_name(block)
        if not name:
            continue
        entities.append((marker, block, name))
    return entities


def _first_number(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return _flat(match.group(1)).strip(" .,;:") if match else None


def _procurement_fields(text: str) -> dict[str, str | None]:
    flat = _flat(text)
    metadata_text = text[:5000]
    metadata_flat = _flat(metadata_text)
    title = _first_number(
        r"\bpn\.\s*[„“\"](.+?)[”\"](?=\s*(?:nr|numer|ogłoszenie|,|\.))",
        flat,
    )
    if not title:
        title = _first_number(
            r"\bpn\.\s*(.+?)(?=\s+(?:nr\s+referencyjny|nr\s+postępowania|"
            r"numer\s+postępowania|ogłoszenie\s+o\s+zamówieniu))",
            flat,
        )

    reference = _first_number(
        r"\b(?:nr\s*(?:referencyjny(?:\s+sprawy)?|postępowania|sprawy)|"
        r"numer\s+postępowania)\s*:?\s*([A-Z0-9][A-Z0-9./_-]{2,})",
        flat,
    )
    bzp_match = re.search(
        r"\b(\d{4})\s*/\s*BZP\s*([0-9]{8,12})(?:\s*/\s*(\d+))?",
        metadata_flat,
        re.IGNORECASE,
    )
    bzp = (
        f"{bzp_match.group(1)}/BZP{bzp_match.group(2)}"
        + (f"/{bzp_match.group(3)}" if bzp_match.group(3) else "")
        if bzp_match
        else None
    )
    ted_match = re.search(r"\b(\d{6})\s*-\s*(\d{4})\b", metadata_flat)
    ted = f"{ted_match.group(1)}-{ted_match.group(2)}" if ted_match else None
    if not ted:
        ted_match = re.search(
            r"\b(\d{4})\s*/\s*S\s*\d{1,3}\s*-\s*(\d{6})\b",
            metadata_flat,
            re.IGNORECASE,
        )
        ted = f"{ted_match.group(2)}-{ted_match.group(1)}" if ted_match else None
    return {
        "numer_bzp": bzp,
        "numer_postepowania": reference,
        "numer_ted": ted,
        "tytul": title,
    }


def extract_odwolanie(text: str) -> dict[str, Any]:
    header_date, place = _header_date_and_place(text)
    action = _first_action(text)
    action_date_match = re.search(_DATE_PATTERN, action, re.IGNORECASE)
    action_date = _parse_date(action_date_match.group()) if action_date_match else None
    reason_id = _reason_id(text)

    sections = _appeal_sections(text)
    appealing_section = sections.get("odwołujący", "")
    appealing_parties = _appeal_entities(appealing_section, "Odwołujący")
    is_consortium = bool(re.search(r"\bkonsorcjum\b", appealing_section, re.I))
    if is_consortium and appealing_parties:
        appealing_parties = appealing_parties[:1]
    buyers = _appeal_entities(sections.get("zamawiający", ""), "Zamawiający")

    appealing: list[dict[str, Any]] = []
    for _, block, name in appealing_parties:
        representative_block = appealing_section if is_consortium else block
        attorneys = _lawyers(representative_block)
        correspondence = re.search(
            r"(?i)\badres\s+do\s+korespondencji\s*:", representative_block
        )
        email_source = (
            representative_block[correspondence.start() :]
            if correspondence
            else representative_block
        )
        emails = re.findall(_EMAIL_PATTERN, email_source, re.IGNORECASE)
        representative = re.search(
            r"(?i)\breprezentowan\w*\s+przez\b", representative_block
        )
        if representative and not correspondence:
            representative_emails = re.findall(
                _EMAIL_PATTERN,
                representative_block[representative.start() :],
                re.IGNORECASE,
            )
            if representative_emails:
                emails = representative_emails
        registry = _registry(block)
        appealing.append(
            {
                "krs": registry["krs"],
                "nazwa": name,
                "nip": registry["nip"],
                "regon": registry["regon"],
                "przez-pelnomocnika": 1 if attorneys else 0,
                "pelnomocnik": (
                    {
                        "imie_nazwisko": attorneys[0],
                        "nazwa": _correspondence_firm(representative_block) or _letterhead_firm(text),
                        "mail": emails[0] if emails else None,
                    }
                    if attorneys
                    else None
                ),
            }
        )

    buyers_output = []
    for marker, block, name in buyers:
        multiple = len(buyers) > 1
        registry = _registry(block)
        is_leader = bool(
            re.search(r"\b(?:Lider|prowadzący postępowanie)\b", marker, re.IGNORECASE)
            or re.search(r"(?i)\bZamawiając\w*\s+prowadząc\w*\s+postępowani", block)
        )
        buyers_output.append(
            {
                "krs": registry["krs"],
                "nazwa": name,
                "nip": registry["nip"],
                "regon": registry["regon"],
                "prowadzacy_postepowanie": (
                    (1 if is_leader else 0) if multiple else None
                ),
            }
        )

    return {
        "OdwolanieKIO": {
            "data": header_date,
            "czynnosc_dzien": action_date,
            "czynnosc_powod_id": reason_id,
            "czynnosc_opis": _REASON_DESCRIPTIONS.get(reason_id),
            "miejscowosc": place,
        },
        "Odwolujacy": appealing,
        "Zamawiajacy": buyers_output,
        "ZamowieniePubliczne": _procurement_fields(text),
    }


def _principal_grant_start(text: str) -> int:
    match = re.search(
        r"\b(?:udzielam|udziela|udzielają|ustanawiam|upoważniam)\s+"
        r"(?:pełnomocnictwa|pełnomocnikiem|pełnomocnictwo)\b",
        text,
        re.IGNORECASE,
    )
    return match.start() if match else min(len(text), 6000)


def _principal_blocks(text: str) -> list[str]:
    prefix = text[: _principal_grant_start(text)]
    consortium = re.search(
        r"(?is)Konsorcjum\)?\s*:\s*(.*?)(?=\(\s*dalej\s+łącznie|"
        r"\bdalej\s+łącznie|,\s*reprezentowani?\b)",
        prefix,
    )
    if consortium:
        blocks = re.findall(
            r"(?is)\d+\)\s*(.*?)(?=;\s*\d+\)\s*|$)",
            consortium.group(1),
        )
        if blocks:
            return [_flat(block).strip(" ;") for block in blocks]

    explicit = re.search(
        r"(?is)Mocodawcą\s+jest\s+(.+?)(?=\.\s*§\s*\d|"
        r"\n\s*§\s*\d|\bPełnomocnik(?:iem|owie|ów)?\b)",
        prefix,
    )
    if explicit:
        return [_flat(explicit.group(1))]

    labeled = re.search(r"(?im)^\s*Mocodawca\s+(.+?)\s*$", prefix)
    if labeled:
        rest = prefix[labeled.start() :]
        boundary = re.search(r"(?im)^\s*(?:Pełnomocnicy\b|§\s*2\b)", rest[1:])
        if boundary:
            rest = rest[: boundary.start() + 1]
        return [rest]

    sole_proprietor = re.search(
        r"(?is)prowadząc\w*\s+działalność\s+gospodarczą\s+pod\s+firmą\s+"
        r"(.+?)(?=,\s*(?:ul\.|NIP\b|REGON\b)|\s+\(dalej)",
        prefix,
    )
    if sole_proprietor:
        return [prefix]

    in_company = re.search(
        r"(?is)\bw\s+imieniu\s+(.+?)"
        r"(?=,\s*(?:ul\.|KRS\b|NIP\b)|\s*\(dalej\b|\s+z\s+siedzibą)",
        prefix,
    )
    if in_company:
        return [prefix]

    company = re.search(
        r"(?im)^[ \t]*(.+?)[ \t]+(?:z\s+siedzibą|,?\s*ul\.|\(\s*KRS\b)",
        prefix,
    )
    if company:
        return [prefix]
    return [prefix] if prefix.strip() else []


def _principal_registry(block: str) -> dict[str, str | None]:
    # "wpisana do rejestru przedsiębiorców KRS" is not a sole proprietor - keep the KRS
    registry = _registry(block, check_sole_proprietor=False)  # tolerates "NIP: 999-295-65-50"
    return {"krs": registry["krs"], "nip": registry["nip"]}


def _principal_data(block: str) -> dict[str, Any]:
    principal = _flat(block).strip(" ,;")
    registry = _principal_registry(principal)
    is_physical = bool(
        re.search(
            r"\b(?:wpisan\w*\s+do\s+CEIDG|prowadząc\w*\s+działalność)\b",
            principal,
            re.IGNORECASE,
        )
    )
    if re.search(
        r"\b(?:spółk[aię]|sp\.\s*(?:z\s*o\.o\.|k\.|j\.|p\.))\b|"
        r"\b(?:S\.A\.|S\.A\b|fundacja|stowarzyszenie)\b",
        principal,
        re.IGNORECASE,
    ):
        is_physical = False
    name = _principal_name(block)
    if name:
        name = re.split(
            r"\s+(?:\(?KRS\b|NIP\b|REGON\b|\(dalej\b|z\s+siedzib\w*\b)",
            name,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" ,;)")

    if is_physical:
        signed_person = re.search(
            rf"Ja,\s*niżej\s+podpisan\w*\s+(?P<name>{_PERSON_NAME_PATTERN})",
            principal,
            re.IGNORECASE,
        )
        if signed_person:
            person_name = _flat(signed_person.group("name"))
        else:
            name_words = (name or "").split()
            person_name = " ".join(name_words[-2:]) if len(name_words) >= 2 else None
    else:
        person_name = None

    type_name = "osoba_fizyczna" if is_physical else "osoba_prawna"
    pesel = re.search(r"\bPESEL\s*:?\s*(\d{11})\b", principal, re.IGNORECASE)
    return {
        "imie_nazwisko": person_name,
        "krs": registry["krs"],
        "nazwa": name or None,
        "nip": registry["nip"],
        "typ": type_name,
        "_pesel": int(pesel.group(1)) if pesel else None,
    }


def _principal_name(block: str) -> str | None:
    raw_lines = block.splitlines()
    for index, line in enumerate(raw_lines[:-1]):
        if re.search(r"(?i)\bMOCODAWCA\s+PEŁNOMOCNIK\b", line):
            candidate_line = raw_lines[index + 1]
            candidate = re.split(r"[ \t]{2,}", candidate_line.strip(), maxsplit=1)[0]
            if candidate and not re.search(r"\b(?:r\.\s*pr\.|adw\.)", candidate, re.I):
                return _flat(candidate.strip(" ,;"))

    flat = _flat(block)
    patterns = (
        r"Mocodawcą\s+jest\s+(.+?)(?=,\s*(?:ul\.|KRS\b|NIP\b|REGON\b)|"
        r"\s*\(dalej\b)",
        r"pod\s+firmą\s+(.+?)(?=,\s*(?:ul\.|KRS\b|NIP\b|REGON\b)|"
        r"\s*\(dalej\b)",
    )
    for pattern in patterns:
        match = re.search(pattern, flat, re.IGNORECASE)
        if match:
            return _flat(match.group(1)).strip(" ,;")

    for line in raw_lines:
        match = re.search(
            r"\bw\s+imieniu\s+(.+?(?:sp\.\s*(?:z\s*o\.o\.|k\.|j\.|p\.)|S\.A\.))"
            r"(?=\s|,|\(|$)",
            line,
            re.IGNORECASE,
        )
        if match:
            return _flat(match.group(1)).strip(" ,;")

    labeled = re.search(r"(?im)^\s*Mocodawca\s+(.+?)\s*$", block)
    if labeled:
        candidate = re.split(
            r"\s+(?:ul\.|KRS\b|NIP\b|REGON\b)", labeled.group(1), maxsplit=1, flags=re.I
        )[0]
        candidate = candidate.strip(" ,;")
        if not re.match(r"^PEŁNOMOCNIK\b", candidate, re.I):
            return _flat(candidate)

    for line in raw_lines[:20]:
        candidate = line.strip(" ,;")
        if candidate and not re.match(
            r"^(?:PEŁNOMOCNICTWO|Mocodawca|Wykonawcy|KRS\b|NIP\b|REGON\b|"
            r"Ja,\s*niżej|Działając\b|przez\b|Postępowanie\b|Zamawiający\b|§\s*\d)",
            candidate,
            re.IGNORECASE,
        ):
            if not re.search(
                r"(?:sp\.\s*(?:z\s*o\.o\.|k\.|j\.|p\.)|S\.A\.)(?=\s|$|,|\()",
                candidate,
                re.IGNORECASE,
            ):
                continue
            for marker in (
                ", ul.",
                " ul.",
                ", KRS",
                " KRS",
                " (KRS",
                " (dalej",
                " z siedzibą",
            ):
                index = candidate.lower().find(marker)
                if index >= 0:
                    candidate = candidate[:index]
            if candidate:
                return _flat(candidate.strip(" ,;"))
    return None


def _lawyer_names(text: str) -> list[str]:
    return list(dict.fromkeys(_flat(match.group("name")) for match in _LAWYER_PATTERN.finditer(text)))


_NOT_A_NAME = re.compile(
    r"(?i)\b(?:signature|verified|dokument|podpisan\w*|www|kancelari\w*|zarząd\w*|prezes\w*|"
    r"prokurent\w*|członek|wiceprezes\w*|spółk\w*|mocodaw\w*|pełnomocni\w*|radca|adwokat|data)\b"
)


def _person(candidate: str) -> str | None:
    """'Szymon Brzozowski - Wiceprezes Zarządu' / 'MATEUSZ WIERZBICKI (adwokat, ...)' -> 'Szymon Brzozowski'."""
    candidate = re.split(r"\s+[–-]\s+|\(|,", _flat(candidate))[0]
    candidate = re.sub(r"(?i)^(?:r\.\s*pr\.|adw\.|radca\s+prawny|adwokat|mec\.)\s+", "", candidate).strip(" .;:")
    words = candidate.split()
    if not 2 <= len(words) <= 3 or _NOT_A_NAME.search(candidate):
        return None
    if not all(re.fullmatch(r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)?", w.capitalize()) for w in words):
        return None
    return " ".join(w if not w.isupper() else w.capitalize() for w in words)


def _granted_names(text: str) -> list[str]:
    """Attorneys listed after 'udziela pełnomocnictwa:' up to 'do reprezentowania'."""
    match = re.search(
        r"(?is)\budziel\w*\s+pełnomocnictw\w*\s*:?\s*(.+?)(?=\bdo\s+(?:reprezentowania|występowania|działania)\b|\bw\s+sprawie\b)",
        text,
    )
    if not match:
        return []
    parts = re.split(r"\n|\s+oraz\s+|\s+i\s+|;", match.group(1))
    return list(dict.fromkeys(name for part in parts if (name := _person(part))))


def _represented_by(text: str) -> list[str]:
    """Signers named in 'reprezentowana przez: A – Prezes Zarządu, B – Członek Zarządu (dalej ...'."""
    match = re.search(r"(?is)\breprezentowan\w*\s+przez\s*:?\s*(.+?)(?=\(\s*dalej|\bniniejszym\b|\budziel)", text)
    if not match:
        return []
    parts = re.split(r",|\s+oraz\s+|\s+i\s+|;", match.group(1))
    return list(dict.fromkeys(name for part in parts if (name := _person(part))))


def _pure_person_line(line: str) -> str | None:
    match = re.fullmatch(rf"\s*({_PERSON_NAME_PATTERN})\s*", line)
    if not match:
        return None
    name = _flat(match.group(1))
    if any(
        token.lower()
        in {
            "pełnomocnictwo",
            "przyjmuję",
            "mocodawca",
            "prezes",
            "zarządu",
            "prokurent",
            "dyrektor",
            "wiceprezes",
            "członek",
            "wspólnik",
            "za",
            "nr",
            "wpisu",
            "dyrektor",
            "prokurent",
            "pieczęć",
        }
        for token in name.split()
    ):
        return None
    return name


def _signer_names(
    text: str, principals: list[str], attorneys: list[str]
) -> list[list[str]]:
    lines = _lines(text)[-30:]
    dotted_lines = [
        index for index, line in enumerate(lines) if re.search(r"\.{3,}|_{3,}", line)
    ]
    if len(principals) > 1:
        sections = list(
            re.finditer(r"(?im)^\s*W\s+imieniu\s+(.+?)\s*:\s*$", text)
        )
        if sections:
            results = [[] for _ in principals]
            for index, marker in enumerate(sections):
                matched_principal = next(
                    (
                        principal_index
                        for principal_index, principal in enumerate(principals)
                        if principal.casefold() in marker.group(1).casefold()
                    ),
                    None,
                )
                if matched_principal is None:
                    continue
                end = (
                    sections[index + 1].start()
                    if index + 1 < len(sections)
                    else len(text)
                )
                region = _lines(text[marker.end() : end])
                separator = next(
                    (
                        line_index
                        for line_index, line in enumerate(region)
                        if re.search(r"\.{3,}|_{3,}", line)
                    ),
                    None,
                )
                if separator is not None:
                    results[matched_principal].extend(
                        name
                        for line in region[separator + 1 :]
                        for name in _signature_person_line(line, attorneys, principals)
                        if name not in attorneys
                    )
            if any(results):
                return [list(dict.fromkeys(names)) for names in results]

    groups = []
    if dotted_lines:
        for index, separator in enumerate(dotted_lines):
            end = dotted_lines[index + 1] if index + 1 < len(dotted_lines) else len(lines)
            groups.append(
                [
                    name
                    for line in lines[separator + 1 : end]
                    for name in _signature_person_line(line, attorneys, principals)
                    if name not in attorneys
                ]
            )
    else:
        groups.append(
            [
                name
                for line in lines[-8:]
                for name in _signature_person_line(line, attorneys, principals)
                if name not in attorneys
            ]
        )
    nonempty_groups = [list(dict.fromkeys(group)) for group in groups if group]
    names = list(dict.fromkeys(name for group in nonempty_groups for name in group))
    return [names] + [[] for _ in principals[1:]]


def _signature_person_line(
    line: str, attorneys: list[str], principals: list[str]
) -> list[str]:
    value = re.sub(r"\.{3,}", " ", line)
    for name in [*attorneys, *principals]:
        value = re.sub(re.escape(name), " ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?:\br\.\s*pr\.|\badw\.)", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\bmiejsce\s+na\s+pieczęć\s+firmową\b", " ", value, flags=re.I)
    value = re.sub(
        r"\b(?:prezes|wiceprezes|zarządu|prokurent|dyrektor|członek|wspólnik)\b.*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b(?:mocodawca|pełnomocnictwo|przyjmuję|za)\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    tokens = value.strip(" .:-").split()
    if not tokens or any(len(token) < 3 for token in tokens) or len(tokens) > 4:
        return []
    whole_name = _pure_person_line(" ".join(tokens))
    if whole_name:
        return [whole_name]
    names = []
    index = 0
    while index < len(tokens):
        for size in (2, 3):
            candidate = " ".join(tokens[index : index + size])
            if len(tokens[index : index + size]) == size:
                person = _pure_person_line(candidate)
                if person:
                    names.append(person)
                    index += size
                    break
        else:
            index += 1
    return names


def extract_pelnomocnictwo(text: str) -> dict[str, Any]:
    principal_blocks = _principal_blocks(text)
    principal_data = [_principal_data(block) for block in principal_blocks]
    attorneys = _lawyer_names(text) or _granted_names(text)
    principal_names = [
        data["nazwa"] for data in principal_data if data["nazwa"] is not None
    ]
    signers = _signer_names(text, principal_names, attorneys)
    if len(principal_data) == 1:
        # real documents: "reprezentowana przez: A – Prezes Zarządu" names the signers explicitly;
        # drop scanner/e-signature noise ("Signature Not Verified") picked up near the bottom
        represented = _represented_by(text[: _principal_grant_start(text) + 40])
        signers = [represented] if represented else [[n for n in (signers[0] if signers else []) if _person(n)]]
    principals = []
    for index, data in enumerate(principal_data):
        signer_names = signers[index] if index < len(signers) else []
        principals.append(
            {
                "data": {key: value for key, value in data.items() if key != "_pesel"},
                "podpisujacy": [{"imie_nazwisko": name} for name in signer_names],
            }
        )

    pesel_match = re.search(r"\bPESEL\s*:?\s*(\d{11})\b", text, re.IGNORECASE)
    pesel = pesel_match.group(1) if pesel_match else None
    return {
        "mocodawca": principals,
        "pelnomocnicy": [
            {"imie_nazwisko": name, "pesel": pesel}
            for name in attorneys
        ],
    }


def _date_after_label(text: str) -> str | None:
    label = re.search(
        r"(?i)\b(?:data\s+(?:operacji|transakcji|wykonania|realizacji|przelewu)|"
        r"wykonano\s+przelew\s+(?:krajowy\s+)?w\s+dniu|"
        r"potwierdza,\s*że\s+w\s+dniu)\b",
        text,
    )
    if label:
        match = re.search(_DATE_PATTERN, text[label.end() : label.end() + 180], re.I)
        if match:
            return _parse_date(match.group())
    # scanned bank forms: "Data\n2026-03-26\nwykonania", "Data operaci\n...", "data wykonania\n20 04 2026"
    for pattern in (
        r"(?im)^\s*Data\s*\n\s*(\d{4}-\d{2}-\d{2})\s*\n\s*(?:wykonania|operac\w*|realizacji)\b",
        r"(?i)\bdata\s+(?:wykonania|operac\w*|realizacji)\b[^\d]{0,80}?(\d{4}-\d{2}-\d{2}|\d{1,2}[ .]\d{2}[ .]\d{4})",
    ):
        match = re.search(pattern, text)
        if match:
            value = re.sub(r"^(\d{1,2})[ .](\d{2})[ .](\d{4})$", r"\3-\2-\1", match.group(1))
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                return value
    return None


def _amount(text: str) -> float | None:
    label = re.compile(
        r"(?i)\b(?:kwota(?:\s+(?:operacji|przelewu|transakcji))?|"
        r"wartość|w\s+kwocie)\b"
    )
    # not glued to letters: "CEN9057564440515" is a transaction id, not an amount
    number = re.compile(r"(?<![\w.,])(\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?)(?![\w])")
    lines = _lines(text)
    for index, line in enumerate(lines):
        match = label.search(line)
        if not match:
            continue
        candidates = [line[match.end() :], *lines[index + 1 : index + 3]]
        for candidate in candidates:
            number_match = number.search(candidate)
            if number_match:
                value = _to_float(re.sub(r"\s", "", number_match.group(1)))
                if value is not None and value < 100_000_000:
                    return value
    # amount with currency anywhere, e.g. "-17,00 PLN" in a statement table
    currency = re.search(r"(?<![\w.,])-?\s?(\d{1,3}(?:[ \u00a0]?\d{3})*[.,]\d{2})\s*(?:PLN|z\u0142)\b", text)
    return _to_float(re.sub(r"\s", "", currency.group(1))) if currency else None


def _to_float(value: str) -> float | None:
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


_ACCOUNT_PATTERN = re.compile(r"((?:PL\s*)?\d(?:[\s-]*\d){25})", re.IGNORECASE)


def _account_after_labels(
    text: str,
    labels: tuple[str, ...],
    opposite_account_labels: str,
    prefer_last: bool = False,
) -> str | None:
    label_pattern = re.compile("|".join(labels), re.IGNORECASE)
    for match in label_pattern.finditer(text):
        tail = text[match.end() : match.end() + 900]
        boundary = re.search(opposite_account_labels, tail, re.IGNORECASE)
        if boundary:
            tail = tail[: boundary.start()]
        accounts = list(_ACCOUNT_PATTERN.finditer(tail))
        if accounts:
            account = (
                accounts[-1] if prefer_last and len(accounts) > 1 else accounts[0]
            )
            digits = re.sub(r"\D", "", account.group(1))
            if len(digits) == 28 and account.group(1).lstrip().upper().startswith("PL"):
                digits = digits[2:]
            if len(digits) == 26:
                return digits
    return None


def _payment_title(text: str) -> str | None:
    lines = _lines(text)
    label_pattern = re.compile(
        r"^(?:tytu[łl]?(?:em)?(?:\s+(?:przelewu|transakcji|operacji|płatności))?|"
        r"opis(?:\s+(?:operacji|transakcji))?)"
        r"\s*:?\s*(.*)$",
        re.I,
    )
    stop_pattern = re.compile(
        r"^(?:data\b|numer\b|nr\s+ref|status\b|kanał\b|typ(?:\s+operacji)?\b|"
        r"tryb\b|waluta\b|opłata(?:/prowizja)?\s*:|kwota\b|rachunek\b|"
        r"data\s+wydruku\b)",
        re.IGNORECASE,
    )
    for index, line in enumerate(lines):
        match = label_pattern.match(line)
        if not match:
            continue
        values = [match.group(1).strip(" .:-")]
        for continuation in lines[index + 1 :]:
            if not continuation:
                if any(values):
                    break
                continue
            if stop_pattern.match(continuation):
                break
            values.append(continuation)
        value = _flat(" ".join(values)).strip(" .:-")
        value = re.sub(r"^[„“\"']|[”\"']$", "", value).strip()
        return value or None
    return None


def extract_przelew(text: str) -> dict[str, Any]:
    flat = _flat(text)
    reference_match = re.search(
        r"(?i)\b(?:numer\s+referencyjny(?:\s+operacji)?|"
        r"numer\s+transakcji(?:\s+operacji)?|"
        r"nr\s+ref\.?(?:\s+operacji)?)\s*[:.]?\s*"
        r"(?=[A-Z/-]*\d)([A-Z0-9][A-Z0-9/-]{5,})",  # must contain a digit (not the word "transakcji")
        flat,
    )
    if not reference_match:  # scanned form: "Numer\n305494\ntransakcji"
        reference_match = re.search(r"(?im)^\s*Numer\s*\n\s*([A-Z0-9/-]*\d[A-Z0-9/-]*)\s*\n\s*transakcji\b", text)
    if not reference_match:
        reference_match = re.search(r"\b(CEN[A-Z0-9-]{8,})\b", flat, re.IGNORECASE)
    sender = _account_after_labels(
        text,
        (
            r"\brachunek\s+obciążany\b",
            r"\brachunek\s+nadawcy\b",
            r"\brachunek\s+zleceniodawcy\b",
            r"\brachunek\s+płatnika\b",
            r"\bz\s+rachunku(?:\s+nr)?\b",
            r"\bpłatnik\b",
            r"\bzleceniodawca\b",
            r"\bnadawca\b",
            r"\bdane\s+nadawcy\b",
        ),
        r"\b(?:rachunek\s+(?:odbiorcy|beneficjenta|uznawany)|na\s+rachunek)\b",
    )
    receiver = _account_after_labels(
        text,
        (
            r"\brachunek\s+odbiorcy\b",
            r"\brachunek\s+beneficjenta\b",
            r"\brachunek\s+uznawany\b",
            r"\bna\s+rachunek(?:\s+nr)?\b",
            r"\bbeneficjent\b",
            r"\badresat\s+przelewu\b",
            r"\bdane\s+odbiorcy\b",
            r"\bodbiorca\b",
        ),
        r"\b(?:rachunek\s+(?:obciążany|nadawcy|zleceniodawcy|płatnika)|"
        r"z\s+rachunku)\b",
        prefer_last=True,
    )
    return {
        "przelew_bankowy": {
            "data_operacji": _date_after_label(text),
            "kwota": _amount(text),
            "na_rachunek": receiver,
            "numer_transakcji": (
                reference_match.group(1) if reference_match else None
            ),
            "tytul": _payment_title(text),
            "z_rachunku": sender,
        }
    }


def extract_document_fields(document_type: str, text: str) -> dict[str, Any]:
    if document_type == "odwolanie":
        return extract_odwolanie(text)
    if document_type == "pelnomocnictwo":
        return extract_pelnomocnictwo(text)
    if document_type == "przelew":
        return extract_przelew(text)
    return {}
