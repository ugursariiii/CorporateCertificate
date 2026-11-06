# -*- coding: utf-8 -*-
"""
Veritabanına ve paylaşılan klasöre dokunmayan birim testleri.

Çalıştırma (kök dizinden):  python -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main  # noqa: E402


class DonemTests(unittest.TestCase):
    def test_bir_yil_geri(self):
        self.assertEqual(main.donem_bir_yil_geri("2025-2026"), "2024-2025")

    def test_bir_yil_geri_gecersiz(self):
        self.assertIsNone(main.donem_bir_yil_geri("2025"))
        self.assertIsNone(main.donem_bir_yil_geri(None))

    def test_donem_gecerli(self):
        self.assertTrue(main.donem_gecerli("2025-2026"))
        for hatali in ("2025-26", "2025-2027", "2026-2025", "abcd-efgh",
                       " 2025-2026", "", None):
            with self.subTest(hatali=hatali):
                self.assertFalse(main.donem_gecerli(hatali))


class FakeDb:
    def __init__(self, kayitlar):
        self.kayitlar = kayitlar
        self.sorgular = []

    def find_activities(self, donem, okul, seviye):
        self.sorgular.append((donem, seviye))
        return self.kayitlar.get((donem, okul, seviye), [])


class RetrospectiveTests(unittest.TestCase):
    def test_12den_lhye_geriye_tarar(self):
        db = FakeDb({("2024-2025", "KOLEJ", "11"): [(7, "Siemens", 2)]})
        rows = main.generate_retrospective(db, "2025-2026", "KOLEJ", "12")

        self.assertEqual(
            db.sorgular,
            [("2025-2026", "12"), ("2024-2025", "11"), ("2023-2024", "10"),
             ("2022-2023", "9"), ("2021-2022", "LH")],
        )
        self.assertEqual(len(rows), 5)
        self.assertIsNone(rows[0]["id"])                 # placeholder satır
        self.assertEqual((rows[1]["id"], rows[1]["dosya_sayisi"]), (7, 2))

    def test_lh_tek_asama(self):
        rows = main.generate_retrospective(FakeDb({}), "2025-2026", "FENLI", "LH")
        self.assertEqual(len(rows), 1)


class YardimciTests(unittest.TestCase):
    def test_saklama_adi_benzersiz_ve_temiz(self):
        a = main.saklama_adi_uret("2025 Siemens Raporu.PDF")
        b = main.saklama_adi_uret("2025 Siemens Raporu.PDF")
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^2025_Siemens_Raporu_[0-9a-f]{8}\.pdf$")

    def test_boyut_metni(self):
        self.assertEqual(main.boyut_metni(1536), "1,5 KB")

    def test_uzanti_izinli(self):
        self.assertTrue(main.uzanti_izinli("a.DOCX"))
        self.assertFalse(main.uzanti_izinli("a.exe"))


class AyarTests(unittest.TestCase):
    def _ini(self, icerik):
        f = tempfile.NamedTemporaryFile("w", suffix=".ini", delete=False,
                                        encoding="utf-8")
        f.write(icerik)
        f.close()
        self.addCleanup(os.remove, f.name)
        return f.name

    def test_ini_okunur_ve_yuzde_bozulmaz(self):
        yol = self._ini("[database]\nuser = app\npassword = a%b!c\n")
        ayar = main.ayarlari_yukle(yol, ortam={})
        self.assertEqual((ayar["user"], ayar["password"]), ("app", "a%b!c"))
        self.assertFalse(ayar["init_schema"])

    def test_ortam_degiskeni_oncelikli(self):
        yol = self._ini("[database]\nuser = app\n")
        ayar = main.ayarlari_yukle(yol, ortam={"CORPCERT_USER": "ortam"})
        self.assertEqual(ayar["user"], "ortam")

    def test_dosya_yoksa_parola_bos(self):
        ayar = main.ayarlari_yukle("olmayan.ini", ortam={})
        self.assertEqual(ayar["password"], "")
        self.assertEqual(ayar["database"], "CorporateCertificate")


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        if self.conn.patlat_on and "activity_files" in sql:
            raise main.pymssql.Error("simüle hata")
        self.conn.calisan.append(sql.split()[2])        # tablo adı
        self.conn.sayac += 1

    def fetchone(self):
        return (self.conn.sayac,)


class _FakeConn:
    def __init__(self, patlat_on=False):
        self.patlat_on = patlat_on
        self.calisan, self.sayac = [], 0
        self.commit_edildi = self.rollback_edildi = False

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commit_edildi = True

    def rollback(self):
        self.rollback_edildi = True

    def close(self):
        pass


class TransactionTests(unittest.TestCase):
    """Çok satırlı kayıtların tek transaction'da yazıldığını doğrular."""

    def _db(self, conn):
        db = main.Database.__new__(main.Database)   # __init__ bağlantı açmasın
        db._connect = lambda: conn
        return db

    def test_kombinasyon_basina_kayit_dosya_bir_kez(self):
        conn = _FakeConn()
        idler = self._db(conn).create_activities(
            "2025-2026", ["FENLI", "KOLEJ"], ["9", "10"], "Siemens",
            [("r.pdf", "r_1.pdf", 10)],
        )
        self.assertEqual(len(idler), 4)
        self.assertEqual(conn.calisan.count("dbo.activities"), 4)
        self.assertEqual(conn.calisan.count("dbo.files"), 1)
        self.assertEqual(conn.calisan.count("dbo.activity_files"), 4)
        self.assertTrue(conn.commit_edildi)

    def test_hata_olursa_rollback(self):
        conn = _FakeConn(patlat_on=True)
        with self.assertRaises(main.pymssql.Error):
            self._db(conn).add_files(1, [("r.pdf", "r_1.pdf", 10)])
        self.assertTrue(conn.rollback_edildi)
        self.assertFalse(conn.commit_edildi)

    def test_init_schema_kapaliyken_ddl_calismaz(self):
        with mock.patch.object(main.Database, "_init_schema") as ddl, \
             mock.patch.object(main.Database, "_fetch") as fetch:
            main.Database("s", "d", "u", "p", init_schema=False)
        ddl.assert_not_called()
        fetch.assert_called_once_with("SELECT 1")


if __name__ == "__main__":
    unittest.main()
