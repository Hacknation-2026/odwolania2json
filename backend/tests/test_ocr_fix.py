from app.extraction.ocr_fix import fix_text


def test_restores_diacritics_lost_by_ocr():
    assert fix_text("Odwotujacy: Zamawiajacy: Biatystok") == "Odwołujący: Zamawiający: Białystok"
    assert fix_text("Wpis od odwotania: 7 500 zt") == "Wpis od odwołania: 7 500 zł"
    assert fix_text("STRAŽY POŽARNEJ") == "STRAŻY POŻARNEJ"


def test_keeps_unknown_and_correct_words():
    assert fix_text("Medicor Infrastruktura S.A., KRS: 9994354396") == "Medicor Infrastruktura S.A., KRS: 9994354396"
    assert fix_text("Odwołujący") == "Odwołujący"
