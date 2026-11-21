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


class RealScanLayoutTests(unittest.TestCase):
    """Layouts seen in the real UZP scans (dane/skany), after OCR text repair."""

    def test_dashed_nip_joint_buyers_and_appeal_list(self) -> None:
        result = extract_document_fields(
            "odwolanie",
            """Białystok, 10.04.2026 r.
Odwołujący:
Medicor Infrastruktura S.A.
KRS: 9994354396, NIP: 999-509-02-81, REGON: 999368597
reprezentowany przez pełnomocnika:
adw. Mateusz Wierzbicki
adres do korespondencji:
Kancelaria Adwokacka adw. Mateusz Wierzbicki
ul. Przemysłowa 64, 20-630 Lublin
Zamawiający:
Zamawiający wspólnie udzielający zamówienia:
1) Zarząd Dróg Powiatowych w Brzozowcu
NIP: 999-239-80-73
– Zamawiający prowadzący postępowanie
2) Zakład Gospodarki Komunalnej w Zielonkowie
REGON: 999806152
Dotyczy:
ODWOŁANIE
wnoszę odwołanie wobec:
1. czynności Zamawiającego polegającej na odrzuceniu oferty Odwołującego, o której Odwołujący
został poinformowany pismem z 1 kwietnia 2026 roku;
2. zaniechania wezwania;
""",
        )
        appeal = result["OdwolanieKIO"]
        self.assertEqual((appeal["czynnosc_powod_id"], appeal["czynnosc_dzien"]), (1, "2026-04-01"))
        party = result["Odwolujacy"][0]
        self.assertEqual(party["nip"], "9995090281")
        self.assertEqual(party["pelnomocnik"]["nazwa"], "Kancelaria Adwokacka adw. Mateusz Wierzbicki")
        buyers = result["Zamawiajacy"]
        self.assertEqual([b["nazwa"] for b in buyers], ["Zarząd Dróg Powiatowych w Brzozowcu", "Zakład Gospodarki Komunalnej w Zielonkowie"])
        self.assertEqual([b["prowadzacy_postepowanie"] for b in buyers], [1, 0])
        self.assertEqual(buyers[0]["nip"], "9992398073")


class RealScanPowerOfAttorneyTests(unittest.TestCase):
    def test_grant_list_representation_and_esignature_noise(self) -> None:
        result = extract_document_fields(
            "pelnomocnictwo",
            """Gdańsk, 27.03.2026 r.
PEŁNOMOCNICTWO
Medicor IT Solutions S.A. z siedzibą w Gdańsk (80-386), ul. Marszałkowska 37, wpisana do
rejestru przedsiębiorców Krajowego Rejestru Sądowego pod numerem KRS: 9991919038, NIP:
999-232-67-54, REGON: 999749508, reprezentowana przez: Zbigniew Cieślak – Prokurent (dalej:
„Mocodawca”), niniejszym udziela pełnomocnictwa:
Grzegorz Kaczmarek (adwokat, nr wpisu PO-17476) oraz KATARZYNA SIKORA (radca prawny, nr
wpisu WR-12316),
do reprezentowania Mocodawcy w sprawie dotyczącej środków ochrony prawnej.
Signature Not Verified
Dokument podpisany przez Zbigniew Cieślak
""",
        )
        principal = result["mocodawca"][0]
        self.assertEqual(principal["data"]["nazwa"], "Medicor IT Solutions S.A.")
        self.assertEqual((principal["data"]["krs"], principal["data"]["nip"]), ("9991919038", "9992326754"))
        self.assertEqual(principal["podpisujacy"], [{"imie_nazwisko": "Zbigniew Cieślak"}])
        self.assertEqual([p["imie_nazwisko"] for p in result["pelnomocnicy"]], ["Grzegorz Kaczmarek", "Katarzyna Sikora"])


class RealScanTransferTests(unittest.TestCase):
    def test_two_line_labels_of_a_scanned_bank_form(self) -> None:
        result = extract_document_fields(
            "przelew",
            """Bank Mazurski
Z rachunku
68 1090 1505 1005 2441 7124 3731
Na rachunek
60 1010 1010 0081 3622 3100 0000
Tytułem
Wpis od odwołania, ZP/12/2026, REGIONALNE CENTRUM ZDROWIA
PUBLICZNEGO W DĘBNICY GÓRNEJ
Kwota
10 000,00 PLN
przelewu
Data
2026-03-26
wykonania
Numer
305494
transakcji
""",
        )["przelew_bankowy"]
        self.assertEqual(result["kwota"], 10000.0)
        self.assertEqual(result["data_operacji"], "2026-03-26")
        self.assertEqual(result["numer_transakcji"], "305494")
        self.assertEqual(result["tytul"], "Wpis od odwołania, ZP/12/2026, REGIONALNE CENTRUM ZDROWIA PUBLICZNEGO W DĘBNICY GÓRNEJ")

    def test_transaction_id_is_not_an_amount(self) -> None:
        result = extract_document_fields("przelew", "Kwota: CEN9057564440515\nKwota operacji -7 500,00 PLN")["przelew_bankowy"]
        self.assertEqual(result["kwota"], 7500.0)
