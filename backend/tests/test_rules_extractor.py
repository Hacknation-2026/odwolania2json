import unittest

from app.extraction.rules import extract_document_fields


class ExtractorTests(unittest.TestCase):
    def test_extracts_the_first_listed_appeal_action(self) -> None:
        result = extract_document_fields(
            "odwolanie",
            """Gdańsk, dnia 3 września 2026 roku
ODWOŁANIE
Zamawiającego, polegających na:
1) wyborze jako najkorzystniejszej oferty, o którym Zamawiający
poinformował wykonawców w dniu 2 września 2026 r.;
2) zaniechaniu odrzucenia oferty.
""",
        )

        self.assertEqual(result["OdwolanieKIO"]["data"], "2026-09-03")
        self.assertEqual(result["OdwolanieKIO"]["miejscowosc"], "Gdańsk")
        self.assertEqual(result["OdwolanieKIO"]["czynnosc_dzien"], "2026-09-02")
        self.assertEqual(result["OdwolanieKIO"]["czynnosc_powod_id"], 2)

    def test_orders_party_fields_like_the_reference_json(self) -> None:
        result = extract_document_fields(
            "odwolanie",
            """ODWOŁANIE
Odwołujący:
Deltawing Usługi sp. j.
KRS: 9990929624
NIP: 9994888947
REGON: 999788508
Zamawiający:
Wexoria Serwis sp. z o.o.
KRS: 9999087092
NIP: 9990199346
REGON: 999007965
""",
        )

        self.assertEqual(
            list(result["Odwolujacy"][0]),
            [
                "krs",
                "nazwa",
                "nip",
                "regon",
                "przez-pelnomocnika",
                "pelnomocnik",
            ],
        )
        self.assertEqual(
            list(result["Zamawiajacy"][0]),
            ["krs", "nazwa", "nip", "regon", "prowadzacy_postepowanie"],
        )

    def test_extracts_transfer_fields_from_labeled_bank_details(self) -> None:
        result = extract_document_fields(
            "przelew",
            """Potwierdzenie przelewu
Płatnik                         Beneficjent
Alpha sp. z o.o.                Beta sp. z o.o.
Rachunek zleceniodawcy: PL 12345678901234567890123456
Rachunek odbiorcy: PL 65432109876543210987654321
Kwota operacji: 200,00 PLN
Data transakcji: 2026-03-21
Nr ref. operacji: CEN2604016344389
Opis
opłata skarbowa od pełnomocnictwa.
""",
        )

        self.assertEqual(
            result["przelew_bankowy"],
            {
                "data_operacji": "2026-03-21",
                "kwota": 200.0,
                "na_rachunek": "65432109876543210987654321",
                "numer_transakcji": "CEN2604016344389",
                "tytul": "opłata skarbowa od pełnomocnictwa",
                "z_rachunku": "12345678901234567890123456",
            },
        )

    def test_assigns_signers_to_the_matching_consortium_principal(self) -> None:
        result = extract_document_fields(
            "pelnomocnictwo",
            """Konsorcjum:
1) Alpha Serwis sp. z o.o. (KRS 1234567890, NIP 1234567890);
2) Beta Serwis sp. z o.o. (KRS 2345678901, NIP 2345678901)
(dalej łącznie „Mocodawcy”) udzielają pełnomocnictwa
r. pr. Jan Kowalski (nr wpisu WA 12345) do reprezentacji.
W imieniu Alpha Serwis sp. z o.o.:
..............................
Anna Nowak
W imieniu Beta Serwis sp. z o.o.:
..............................
Marek Lis
Pełnomocnictwo przyjmuję:
..............................
r. pr. Jan Kowalski
""",
        )

        principals = result["mocodawca"]
        self.assertEqual(
            [principal["data"]["nazwa"] for principal in principals],
            ["Alpha Serwis sp. z o.o.", "Beta Serwis sp. z o.o."],
        )
        self.assertEqual(
            [
                [signer["imie_nazwisko"] for signer in principal["podpisujacy"]]
                for principal in principals
            ],
            [["Anna Nowak"], ["Marek Lis"]],
        )
        self.assertEqual(
            result["pelnomocnicy"],
            [{"imie_nazwisko": "Jan Kowalski", "pesel": None}],
        )


if __name__ == "__main__":
    unittest.main()
