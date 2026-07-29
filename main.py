# -*- coding: utf-8 -*-
"""
Kurumsal İletişim Sertifika Programı
========================================================
Okulun "Kurumsal İletişim (Corporate Communications)" birimi için geliştirilmiş,
kurumsal sertifika programlarını (Siemens, Cervantes, Özyeğin vb.) takip eden
modern bir masaüstü uygulamasıdır.

Tek dosyada hem MSSQL veri yönetimini hem de PyQt6 arayüzünü birleştirir.

Bağımlılıklar:
    pip install PyQt6 pymssql

Not: MSSQL erişimi için pyodbc yerine pymssql kullanılır. pymssql, TDS
istemcisini (FreeTDS) kendi içinde taşır; böylece uygulamanın kurulacağı
makineye ayrıca "ODBC Driver for SQL Server" kurmak gerekmez ve PyInstaller
ile üretilen exe tek başına her Windows makinesinde çalışır.
"""

import os
import re
import csv
import sys
import uuid
import ctypes
import shutil
from html import escape
from datetime import datetime
from contextlib import closing

import pymssql

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import (
    QFont, QIcon, QDesktopServices, QTextDocument, QPageSize, QPageLayout,
)
from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewDialog
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QGroupBox, QFrame,
    QAbstractItemView, QStatusBar, QCheckBox, QListWidget, QListWidgetItem,
    QFileDialog, QDialog,
)

# ---------------------------------------------------------------------------
# SABİTLER (Domain kuralları)
# ---------------------------------------------------------------------------

# --- MSSQL bağlantı ayarları ------------------------------------------------
# Uygulama, hangi makinede çalışırsa çalışsın veriyi daima aşağıdaki merkezî
# SQL Server 2022 sunucusundan okur/yazar; yerel bir veritabanı dosyası yoktur.
# Tablolar açılışta (yoksa) oluşturulur. Bkz. schema.sql
#
# Ayarlar ortam değişkeniyle geçersiz kılınabilir: böylece exe'yi yeniden
# derlemeden farklı bir sunucuya (ör. test ortamı) yönlendirilebilir.
DB_SERVER = os.environ.get("CORPCERT_SERVER", "94.102.74.165")
DB_NAME = os.environ.get("CORPCERT_DB", "CorporateCertificate")
DB_USER = os.environ.get("CORPCERT_USER", "sa")
DB_PASSWORD = os.environ.get("CORPCERT_PASSWORD", "GcUC7w@DA3!?Kvjqhyb!!")

# Bağlantı kurulamazsa kullanıcıyı süresiz bekletmemek için (saniye).
LOGIN_TIMEOUT = 15   # oturum açma aşaması
QUERY_TIMEOUT = 30   # sorgu çalışma süresi

# Okul seçenekleri
OKULLAR = ["FENLI", "KOLEJ"]

# Seviye sıralaması (azalan kronolojik tarama için kullanılır).
# Mantık: 12 -> 11 -> 10 -> 9 -> LH şeklinde geriye doğru azalır.
# "LH" (Hazırlık/Prep) en alt seviyedir ve döngünün durma noktasıdır.
SEVIYELER = ["LH", "9", "10", "11", "12"]

# Geriye doğru tarama için seviyenin bir alt basamağını veren harita.
# 9'un altı doğrudan LH'dir (9'dan küçük seviye Hazırlık sınıfıdır).
ONCEKI_SEVIYE = {
    "12": "11",
    "11": "10",
    "10": "9",
    "9": "LH",
    "LH": None,  # LH en alt seviyedir; bir öncesi yoktur -> döngü durur.
}

# --- Dosya eki ayarları -----------------------------------------------------
# Kayda eklenen dosyalar veritabanına değil, aşağıdaki paylaşılan ağ klasörüne
# kopyalanır; veritabanında yalnızca dosyanın adı/boyutu ve klasördeki saklanan
# adı tutulur. Klasör, DB ayarları gibi ortam değişkeniyle değiştirilebilir.
DOSYA_KLASORU = os.environ.get(
    "CORPCERT_DOSYA_KLASORU",
    r"\\172.16.0.201\Kurumsal_Video\ProgramFiles\CorporateCertificate\dosyalar",
)

# Yüklenmesine izin verilen dosya türleri (uzantı -> pencerede görünen etiket).
# Yeni bir tür açmak için tek yapılması gereken buraya eklemektir; hem doğrulama
# hem de dosya seçme penceresinin filtresi bu haritadan üretilir.
IZINLI_UZANTILAR = {
    ".pdf": "PDF",
    ".doc": "Word", ".docx": "Word",
    ".xls": "Excel", ".xlsx": "Excel", ".xlsm": "Excel",
    ".ppt": "PowerPoint", ".pptx": "PowerPoint",
    ".txt": "Metin",
}

# Tek bir dosyanın azami boyutu (bayt). Kopyalama ağ üzerinden yapıldığından,
# yanlışlıkla seçilen devasa bir dosyanın arayüzü kilitlemesini engeller.
MAX_DOSYA_BOYUTU = 50 * 1024 * 1024  # 50 MB


# ---------------------------------------------------------------------------
# VERİTABANI KATMANI (MSSQL / pymssql)
# ---------------------------------------------------------------------------

# Tablo DDL'i: schema.sql ile birebir aynıdır. sqlcmd olmadan da (uygulama ilk
# açıldığında) şemanın kurulabilmesi için burada da tutulur. GO ayracı sqlcmd'e
# özgü olduğundan ifadeler ayrı ayrı çalıştırılır.
DDL_STATEMENTS = [
    """
    IF OBJECT_ID(N'dbo.activities', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.activities (
            id            INT IDENTITY(1,1) NOT NULL,
            donem         NVARCHAR(9)   NOT NULL,
            okul          NVARCHAR(50)  NOT NULL,
            seviye        NVARCHAR(10)  NOT NULL,
            etkinlik_adi  NVARCHAR(255) NOT NULL,
            CONSTRAINT PK_activities PRIMARY KEY CLUSTERED (id)
        );
    END
    """,
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'IX_activities_donem_okul_seviye'
          AND object_id = OBJECT_ID(N'dbo.activities')
    )
    BEGIN
        CREATE NONCLUSTERED INDEX IX_activities_donem_okul_seviye
            ON dbo.activities (donem, okul, seviye)
            INCLUDE (etkinlik_adi);
    END
    """,
    """
    IF OBJECT_ID(N'dbo.files', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.files (
            id              INT IDENTITY(1,1) NOT NULL,
            dosya_adi       NVARCHAR(255)  NOT NULL,
            saklanan_ad     NVARCHAR(260)  NOT NULL,
            boyut           INT            NOT NULL,
            yuklenme_tarihi DATETIME2(0)   NOT NULL
                CONSTRAINT DF_files_yuklenme_tarihi DEFAULT SYSDATETIME(),
            CONSTRAINT PK_files PRIMARY KEY CLUSTERED (id)
        );
    END
    """,
    # Dosyalar bir zamanlar VARBINARY olarak veritabanında saklanıyordu; eski
    # şemaya sahip bir veritabanına karşı çalışılırsa kolon burada eklenir.
    """
    IF COL_LENGTH('dbo.files', 'saklanan_ad') IS NULL
        ALTER TABLE dbo.files ADD saklanan_ad NVARCHAR(260) NULL;
    """,
    """
    IF OBJECT_ID(N'dbo.activity_files', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.activity_files (
            activity_id INT NOT NULL,
            file_id     INT NOT NULL,
            CONSTRAINT PK_activity_files PRIMARY KEY CLUSTERED (activity_id, file_id),
            CONSTRAINT FK_activity_files_activity FOREIGN KEY (activity_id)
                REFERENCES dbo.activities (id) ON DELETE CASCADE,
            CONSTRAINT FK_activity_files_file FOREIGN KEY (file_id)
                REFERENCES dbo.files (id) ON DELETE CASCADE
        );
    END
    """,
    """
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'IX_activity_files_file'
          AND object_id = OBJECT_ID(N'dbo.activity_files')
    )
    BEGIN
        CREATE NONCLUSTERED INDEX IX_activity_files_file
            ON dbo.activity_files (file_id);
    END
    """,
]

# Hiçbir kayda bağlı kalmayan dosya satırlarını siler ve paylaşılan klasörden de
# kaldırılabilmeleri için saklanan adlarını geri döndürür (OUTPUT DELETED).
SAHIPSIZ_DOSYA_TEMIZLIGI = (
    "DELETE f OUTPUT DELETED.saklanan_ad FROM dbo.files AS f "
    "WHERE NOT EXISTS (SELECT 1 FROM dbo.activity_files AS af WHERE af.file_id = f.id)"
)


# ---------------------------------------------------------------------------
# DOSYA DEPOSU (paylaşılan ağ klasörü)
# ---------------------------------------------------------------------------

def depo_klasoru():
    """Dosya klasörünü (yoksa oluşturarak) döndürür."""
    os.makedirs(DOSYA_KLASORU, exist_ok=True)
    return DOSYA_KLASORU


def depo_yolu(saklanan_ad):
    """Paylaşılan klasördeki bir dosyanın tam yolunu verir."""
    return os.path.join(DOSYA_KLASORU, saklanan_ad)


def uzanti_izinli(dosya_adi):
    """Dosya türünün yüklenmesine izin verilip verilmediğini söyler."""
    return os.path.splitext(dosya_adi)[1].lower() in IZINLI_UZANTILAR


def saklama_adi_uret(dosya_adi):
    """
    Paylaşılan klasörde kullanılacak, çakışmayan bir dosya adı üretir:
    "2025 Siemens Raporu.pdf" -> "2025_Siemens_Raporu_9f3c1ab2.pdf"

    Aynı adlı dosyaların birbirinin üzerine yazmaması için sonuna rastgele bir
    ek konur; kullanıcıya gösterilen özgün ad veritabanında ayrıca saklanır.
    """
    kok, uzanti = os.path.splitext(os.path.basename(dosya_adi))
    temiz = re.sub(r"[^\w.-]+", "_", kok, flags=re.UNICODE).strip("._")[:80]
    return f"{temiz or 'dosya'}_{uuid.uuid4().hex[:8]}{uzanti.lower()}"


def depoya_kopyala(kaynak_yol, saklanan_ad):
    """Dosyayı paylaşılan klasöre kopyalar ve hedef yolu döndürür."""
    hedef = os.path.join(depo_klasoru(), saklanan_ad)
    shutil.copyfile(kaynak_yol, hedef)
    return hedef


def depodan_sil(saklanan_adlar):
    """
    Verilen dosyaları paylaşılan klasörden siler. Klasöre o an erişilemiyorsa
    ya da dosya elle silinmişse sessizce geçilir: veritabanı tarafı zaten
    temizlenmiştir ve silme işleminin bu yüzden başarısız sayılması istenmez.
    """
    for ad in saklanan_adlar:
        if not ad:
            continue
        try:
            os.remove(depo_yolu(ad))
        except OSError:
            pass


class Database:
    """
    Tüm MSSQL işlemlerini yöneten yardımcı sınıf.

    pymssql'de parametre yer tutucusu "?" değil "%s"dir. Değerler yine sürücü
    tarafından bağlanır (string birleştirme yapılmaz), yani SQL injection'a
    karşı korunma aynıdır.
    """

    def __init__(self, server=DB_SERVER, database=DB_NAME,
                 user=DB_USER, password=DB_PASSWORD):
        self.server = server
        self.database = database
        self.user = user
        self.password = password
        self._init_schema()

    def _connect(self):
        """Veritabanına bağlantı açar (her işlem için yeni bağlantı)."""
        return pymssql.connect(
            server=self.server,
            database=self.database,
            user=self.user,
            password=self.password,
            charset="UTF-8",          # Türkçe karakterlerin bozulmaması için
            login_timeout=LOGIN_TIMEOUT,
            timeout=QUERY_TIMEOUT,
        )

    def _fetch(self, sql, params=None):
        """SELECT çalıştırır ve satırları düz demet listesi olarak döndürür."""
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return [tuple(row) for row in cur.fetchall()]

    def _execute(self, sql, params=None):
        """INSERT/DELETE gibi yazma işlemlerini çalıştırıp commit eder."""
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            conn.commit()

    def _insert_returning_id(self, sql, params):
        """
        INSERT ... OUTPUT INSERTED.id çalıştırır ve oluşan kimliği döndürür.
        (SCOPE_IDENTITY() yerine OUTPUT kullanılır: tek sonuç kümesi döndüğü
        için pymssql'de ayrıca nextset() gezinmesi gerekmez.)
        """
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()
            return int(row[0])

    def _init_schema(self):
        """dbo.activities tablosunu ve indeksini (yoksa) oluşturur."""
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            for ddl in DDL_STATEMENTS:
                cur.execute(ddl)
            conn.commit()

    def add_activity(self, donem, okul, seviye, etkinlik_adi):
        """Yeni bir kurumsal sertifika kaydı ekler ve oluşan id'yi döndürür."""
        return self._insert_returning_id(
            "INSERT INTO dbo.activities (donem, okul, seviye, etkinlik_adi) "
            "OUTPUT INSERTED.id VALUES (%s, %s, %s, %s)",
            (donem, okul, seviye, etkinlik_adi),
        )

    def find_activities(self, donem, okul, seviye):
        """
        Belirli dönem/okul/seviye için kayıtlı (id, etkinlik_adi, dosya_sayisi)
        üçlülerini döndürür. Aynı kombinasyonda birden fazla kayıt olabileceğinden
        liste döner.
        """
        return self._fetch(
            "SELECT a.id, a.etkinlik_adi, "
            "       (SELECT COUNT(*) FROM dbo.activity_files AS af "
            "        WHERE af.activity_id = a.id) "
            "FROM dbo.activities AS a "
            "WHERE a.donem = %s AND a.okul = %s AND a.seviye = %s",
            (donem, okul, seviye),
        )

    def distinct_donemler(self):
        """Veritabanında kayıtlı tüm dönemleri (azalan sırada) döndürür."""
        return [
            row[0] for row in self._fetch(
                "SELECT DISTINCT donem FROM dbo.activities ORDER BY donem DESC"
            )
        ]

    def get_all_activities(self):
        """
        Tüm kayıtları (id dahil) en yeni dönem üstte olacak şekilde döndürür.
        Silme işlemi için id bilgisine ihtiyaç duyulur.
        """
        return self._fetch(
            "SELECT id, donem, okul, seviye, etkinlik_adi FROM dbo.activities "
            "ORDER BY donem DESC, okul, seviye"
        )

    def delete_activity(self, activity_id):
        """
        Verilen id'ye sahip kaydı siler. Kayıt-dosya bağları FK üzerinden
        (ON DELETE CASCADE) kendiliğinden düşer; başka kayda bağlı kalmayan
        dosyalar hem veritabanından hem paylaşılan klasörden temizlenir.
        """
        self._execute("DELETE FROM dbo.activities WHERE id = %s", (activity_id,))
        depodan_sil(self._sahipsiz_dosyalari_temizle())

    # --- Dosya ekleri -------------------------------------------------------

    def add_file(self, dosya_adi, saklanan_ad, boyut):
        """
        Paylaşılan klasöre kopyalanmış bir dosyanın kaydını oluşturur ve dosya
        id'sini döndürür. Dosyanın kendisi burada değil, depoya_kopyala() ile
        klasöre yazılır.
        """
        return self._insert_returning_id(
            "INSERT INTO dbo.files (dosya_adi, saklanan_ad, boyut) "
            "OUTPUT INSERTED.id VALUES (%s, %s, %s)",
            (dosya_adi, saklanan_ad, boyut),
        )

    def _sahipsiz_dosyalari_temizle(self):
        """
        Artık hiçbir kayda bağlı olmayan dosya satırlarını siler ve klasörden de
        kaldırılabilmeleri için saklanan adlarını döndürür.
        """
        with closing(self._connect()) as conn:
            cur = conn.cursor()
            cur.execute(SAHIPSIZ_DOSYA_TEMIZLIGI)
            adlar = [row[0] for row in cur.fetchall()]
            conn.commit()
            return adlar

    def link_file(self, activity_id, file_id):
        """Var olan bir dosyayı bir kayda bağlar (içerik kopyalanmaz)."""
        self._execute(
            "INSERT INTO dbo.activity_files (activity_id, file_id) VALUES (%s, %s)",
            (activity_id, file_id),
        )

    def list_files(self, activity_id):
        """
        Bir kayda ekli dosyaları
        (id, ad, saklanan_ad, boyut, yüklenme tarihi) olarak döndürür.
        """
        return self._fetch(
            "SELECT f.id, f.dosya_adi, f.saklanan_ad, f.boyut, f.yuklenme_tarihi "
            "FROM dbo.files AS f "
            "JOIN dbo.activity_files AS af ON af.file_id = f.id "
            "WHERE af.activity_id = %s "
            "ORDER BY f.yuklenme_tarihi, f.id",
            (activity_id,),
        )

    def unlink_file(self, activity_id, file_id):
        """
        Dosyayı bir kayıttan koparır. Dosya başka bir kayda da bağlıysa klasörde
        durmaya devam eder; hiçbir kayda bağlı kalmadıysa klasörden de silinir.
        """
        self._execute(
            "DELETE FROM dbo.activity_files WHERE activity_id = %s AND file_id = %s",
            (activity_id, file_id),
        )
        depodan_sil(self._sahipsiz_dosyalari_temizle())


# ---------------------------------------------------------------------------
# DÖNEM YARDIMCI FONKSİYONLARI
# ---------------------------------------------------------------------------

def donem_bir_yil_geri(donem):
    """
    "2025-2026" -> "2024-2025" şeklinde dönemi bir yıl geriye alır.
    Geçersiz formatta None döner (güvenli durdurma için).
    """
    try:
        bas, son = donem.split("-")
        return f"{int(bas) - 1}-{int(son) - 1}"
    except (ValueError, AttributeError):
        return None


def _dosya_filtresi():
    """
    IZINLI_UZANTILAR haritasından QFileDialog filtre metnini üretir; böylece
    izinli türler tek bir yerde tanımlı kalır:
        "Desteklenen dosyalar (*.pdf *.doc ...);;PDF (*.pdf);;Word (*.doc *.docx);;..."
    """
    gruplar = {}
    for uzanti, etiket in IZINLI_UZANTILAR.items():
        gruplar.setdefault(etiket, []).append("*" + uzanti)
    hepsi = " ".join("*" + uzanti for uzanti in IZINLI_UZANTILAR)
    parcalar = [f"Desteklenen dosyalar ({hepsi})"]
    parcalar += [f"{etiket} ({' '.join(k)})" for etiket, k in gruplar.items()]
    return ";;".join(parcalar)


DOSYA_FILTRESI = _dosya_filtresi()

# Kullanıcıya gösterilen tür listesi: "PDF, Word, Excel, PowerPoint, Metin"
IZINLI_TURLER_METNI = ", ".join(dict.fromkeys(IZINLI_UZANTILAR.values()))


def boyut_metni(bayt):
    """1536 -> "1,5 KB" gibi okunabilir bir dosya boyutu metni üretir."""
    deger = float(bayt)
    for birim in ("B", "KB", "MB", "GB"):
        if deger < 1024 or birim == "GB":
            return f"{deger:.1f} {birim}".replace(".", ",")
        deger /= 1024


# ---------------------------------------------------------------------------
# RAPORLAMA ALGORİTMASI (Retrospective Tracking)
# ---------------------------------------------------------------------------

def generate_retrospective(db, donem, okul, seviye):
    """
    Seçilen dönem/okul/seviyeden başlayarak geriye doğru kronolojik tarama yapar.

    Her aşamada:
      - mevcut dönem/seviye için sertifika aranır,
      - dönem 1 yıl geri alınır, seviye bir alt basamağa indirilir (12->11->...->9->LH),
      - seviye LH'a inip işlendikten sonra döngü güvenli şekilde biter.

    Dönüş: tabloya basılmak üzere satır listesi (dict).
    """
    sonuclar = []
    mevcut_donem = donem
    mevcut_seviye = seviye
    asama = 1

    while True:
        # Güvenlik: dönem formatı bozulduysa dur.
        if mevcut_donem is None:
            break

        etkinlikler = db.find_activities(mevcut_donem, okul, mevcut_seviye)

        if etkinlikler:
            for activity_id, ad, dosya_sayisi in etkinlikler:
                sonuclar.append({
                    "id": activity_id,
                    "asama": asama,
                    "donem": mevcut_donem,
                    "okul": okul,
                    "seviye": mevcut_seviye,
                    "etkinlik": ad,
                    "dosya_sayisi": dosya_sayisi,
                })
        else:
            # Kayıt bulunamasa da aşamayı raporda göstermek izlenebilirlik sağlar.
            sonuclar.append({
                "id": None,
                "asama": asama,
                "donem": mevcut_donem,
                "okul": okul,
                "seviye": mevcut_seviye,
                "etkinlik": "— (Kayıt bulunamadı)",
                "dosya_sayisi": 0,
            })

        # Durdurma koşulu: LH'a ulaşıldıysa (ve işlendiyse) döngü biter.
        if mevcut_seviye == "LH":
            break

        # Bir sonraki (daha eski) aşamaya geç.
        sonraki_seviye = ONCEKI_SEVIYE.get(mevcut_seviye)
        if sonraki_seviye is None:
            break

        mevcut_donem = donem_bir_yil_geri(mevcut_donem)
        mevcut_seviye = sonraki_seviye
        asama += 1

    return sonuclar


# ---------------------------------------------------------------------------
# QSS - KURUMSAL TASARIM (Qt Style Sheet)
# ---------------------------------------------------------------------------

CORPORATE_QSS = """
* {
    font-family: "Segoe UI", "Calibri", sans-serif;
    font-size: 13px;
    color: #1f2933;
}
QMainWindow, QWidget {
    background-color: #f4f6f8;
}
QTabWidget::pane {
    border: 1px solid #d2d9e0;
    border-radius: 8px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: #e4e9ef;
    color: #52606d;
    padding: 10px 22px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #1d3557;
    color: #ffffff;
}
QTabBar::tab:hover:!selected {
    background: #cdd6df;
}
QGroupBox {
    border: 1px solid #d2d9e0;
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px;
    font-weight: 600;
    background: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #1d3557;
}
QLabel#HeaderTitle {
    background: transparent;
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#HeaderSubtitle {
    background: transparent;
    font-size: 12px;
    color: #c9d6e3;
}
QFrame#HeaderBar {
    background: #1d3557;
    border-radius: 10px;
}
QLineEdit, QComboBox {
    border: 1px solid #c4ccd4;
    border-radius: 6px;
    padding: 7px 10px;
    background: #ffffff;
    min-height: 18px;
}
QLineEdit:focus, QComboBox:focus {
    border: 1px solid #2a9d8f;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QPushButton {
    background: #2a9d8f;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 9px 18px;
    font-weight: 600;
}
QPushButton:hover {
    background: #248277;
}
QPushButton:pressed {
    background: #1e6b62;
}
QPushButton#SecondaryBtn {
    background: #457b9d;
}
QPushButton#SecondaryBtn:hover {
    background: #3a6a88;
}
QPushButton#GhostBtn {
    background: #ffffff;
    color: #1d3557;
    border: 1px solid #1d3557;
}
QPushButton#GhostBtn:hover {
    background: #eaf0f6;
}
QListWidget {
    border: 1px solid #c4ccd4;
    border-radius: 6px;
    background: #ffffff;
    padding: 4px;
}
QListWidget::item {
    padding: 5px 6px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background: #cdeae6;
    color: #1f2933;
}
QDialog {
    background: #f4f6f8;
}
QTableWidget {
    border: 1px solid #d2d9e0;
    border-radius: 6px;
    gridline-color: #e4e9ef;
    background: #ffffff;
    selection-background-color: #cdeae6;
    selection-color: #1f2933;
}
QHeaderView::section {
    background: #1d3557;
    color: #ffffff;
    padding: 8px;
    border: none;
    font-weight: 600;
}
QStatusBar {
    background: #e4e9ef;
    color: #52606d;
}
"""


# ---------------------------------------------------------------------------
# ARAYÜZ - EKLİ DOSYALAR PENCERESİ
# ---------------------------------------------------------------------------

class EkDosyalarDialog(QDialog):
    """
    Bir kayda bağlı dosya eklerini listeler; seçilen eki açmayı, diske
    kaydetmeyi veya kayıttan silmeyi sağlar.
    """

    def __init__(self, parent, db, activity_id, baslik):
        super().__init__(parent)
        self.db = db
        self.activity_id = activity_id
        # Silme yapıldıysa çağıran taraf raporu tazeleyebilsin diye işaretlenir.
        self.degisti = False

        self.setWindowTitle("Ekli Dosyalar")
        self.resize(560, 340)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        baslik_lbl = QLabel(baslik)
        baslik_lbl.setStyleSheet("font-weight:600; color:#1d3557;")
        baslik_lbl.setWordWrap(True)
        lay.addWidget(baslik_lbl)

        self.liste = QListWidget()
        lay.addWidget(self.liste)

        btns = QHBoxLayout()
        ac_btn = QPushButton("Aç")
        ac_btn.clicked.connect(self._on_open)
        # "Farklı Kaydet" butonu gizlendi; işleyicisi (_on_save_as) yeniden
        # gerekirse bağlanmak üzere duruyor.
        sil_btn = QPushButton("Kayıttan Sil")
        sil_btn.setObjectName("GhostBtn")
        sil_btn.clicked.connect(self._on_delete)
        kapat_btn = QPushButton("Kapat")
        kapat_btn.setObjectName("GhostBtn")
        kapat_btn.clicked.connect(self.accept)

        for b in (ac_btn, sil_btn):
            btns.addWidget(b)
        btns.addStretch()
        btns.addWidget(kapat_btn)
        lay.addLayout(btns)

        self._reload()

    def _reload(self):
        """Ek listesini veritabanından tazeler."""
        self.liste.clear()
        try:
            kayitlar = self.db.list_files(self.activity_id)
        except pymssql.Error as exc:
            QMessageBox.critical(self, "Veritabanı Hatası", str(exc))
            return

        if not kayitlar:
            self.liste.addItem("(Bu kayda ekli dosya yok)")
            return

        for file_id, ad, saklanan_ad, boyut, tarih in kayitlar:
            item = QListWidgetItem(
                f"{ad}    •    {boyut_metni(boyut)}    •    {tarih:%d.%m.%Y %H:%M}"
            )
            item.setData(Qt.ItemDataRole.UserRole, (file_id, ad, saklanan_ad))
            self.liste.addItem(item)

    def _secili_dosya(self):
        """Seçili satırın (file_id, ad, saklanan_ad) bilgisini verir; seçim yoksa None."""
        item = self.liste.currentItem()
        veri = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not veri:
            # "(Bu kayda ekli dosya yok)" satırında UserRole verisi bulunmaz.
            QMessageBox.information(
                self, "Seçim Yok", "Lütfen listeden bir dosya seçin."
            )
            return None
        return veri

    def _kaynak_yol(self, saklanan_ad):
        """
        Dosyanın paylaşılan klasördeki yolunu doğrulayarak döndürür.
        Klasöre erişilemiyorsa ya da dosya elle silinmişse None döner.
        """
        yol = depo_yolu(saklanan_ad)
        try:
            varmi = os.path.isfile(yol)
        except OSError:
            varmi = False
        if not varmi:
            QMessageBox.warning(
                self, "Dosya Bulunamadı",
                f"Dosya paylaşılan klasörde bulunamadı:\n{yol}\n\n"
                "Klasöre erişiminizi kontrol edin; dosya taşınmış ya da "
                "silinmiş olabilir.",
            )
            return None
        return yol

    def _on_open(self):
        """Dosyayı paylaşılan klasörden, varsayılan uygulamasıyla açar."""
        veri = self._secili_dosya()
        if not veri:
            return
        _file_id, _ad, saklanan_ad = veri
        yol = self._kaynak_yol(saklanan_ad)
        if yol:
            QDesktopServices.openUrl(QUrl.fromLocalFile(yol))

    def _on_save_as(self):
        """Dosyanın bir kopyasını kullanıcının seçtiği yere kaydeder."""
        veri = self._secili_dosya()
        if not veri:
            return
        _file_id, ad, saklanan_ad = veri
        kaynak = self._kaynak_yol(saklanan_ad)
        if not kaynak:
            return
        hedef, _ = QFileDialog.getSaveFileName(self, "Dosyayı Kaydet", ad)
        if not hedef:
            return
        try:
            shutil.copyfile(kaynak, hedef)
        except OSError as exc:
            QMessageBox.warning(self, "Dosya Kaydedilemedi", str(exc))
            return
        QMessageBox.information(self, "Kaydedildi", f"Dosya kaydedildi:\n{hedef}")

    def _on_delete(self):
        veri = self._secili_dosya()
        if not veri:
            return
        file_id, ad, _saklanan_ad = veri
        cevap = QMessageBox.question(
            self, "Eki Sil",
            f"'{ad}' bu kayıttan silinsin mi?\n\n"
            "Dosya başka bir kayıtta kullanılmıyorsa paylaşılan klasörden de "
            "kaldırılır.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return
        try:
            self.db.unlink_file(self.activity_id, file_id)
        except pymssql.Error as exc:
            QMessageBox.critical(self, "Veritabanı Hatası", str(exc))
            return
        self.degisti = True
        self._reload()


# ---------------------------------------------------------------------------
# ARAYÜZ - ANA PENCERE
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()

        self.setWindowTitle("Kurumsal İletişim Sertifika Programı")
        self.resize(960, 680)
        self._apply_native_titlebar_color()

        # Merkezi yerleşim
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        root_layout.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_management_panel(), "Yeni Kayıt Ekle")
        self.tabs.addTab(self._build_query_panel(), "Listele")
        root_layout.addWidget(self.tabs)

        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"Hazır • Veritabanı: {DB_NAME} @ {DB_SERVER}")

        # Açılışta dönem combobox'larını doldur.
        self._refresh_donem_combos()

    def _apply_native_titlebar_color(self):
        """
        Windows'un çizdiği native pencere başlık çubuğu (caption) QSS ile
        boyanamaz; bunun için DWM (Desktop Window Manager) API'sini kullanmak
        gerekir. Windows 11 (build 22000+) üzerinde caption zeminini
        #f4f6f8 (uygulamanın gövde rengiyle aynı) yapar, yazıyı koyu tutar.
        Desteklenmeyen Windows sürümlerinde sessizce yoksayılır.
        """
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            dwmapi = ctypes.windll.dwmapi

            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36

            def to_colorref(hex_color):
                hex_color = hex_color.lstrip("#")
                r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
                return r | (g << 8) | (b << 16)  # COLORREF: 0x00BBGGRR

            caption_color = ctypes.c_int(to_colorref("f4f6f8"))
            text_color = ctypes.c_int(to_colorref("1f2933"))

            dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), DWMWA_CAPTION_COLOR,
                ctypes.byref(caption_color), ctypes.sizeof(caption_color),
            )
            dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), DWMWA_TEXT_COLOR,
                ctypes.byref(text_color), ctypes.sizeof(text_color),
            )
        except (OSError, AttributeError, ValueError):
            # Eski Windows sürümleri (Win10 vb.) bu API'yi desteklemez;
            # bu durumda varsayılan native başlık rengi kullanılmaya devam eder.
            pass

    # ----- Üst Başlık Çubuğu -------------------------------------------------
    def _build_header(self):
        bar = QFrame()
        bar.setObjectName("HeaderBar")
        # QFrame, QSS arkaplan rengini varsayılan olarak boyamaz; bu öznitelik
        # olmadan zemin beyaz kalır ve üstündeki beyaz yazı görünmez olurdu.
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(2)

        title = QLabel("Kurumsal İletişim Sertifika Programı")
        title.setObjectName("HeaderTitle")
        subtitle = QLabel(
            ""
        )
        subtitle.setObjectName("HeaderSubtitle")

        lay.addWidget(title)
        lay.addWidget(subtitle)
        return bar

    # ----- A) Management Panel (Veri Girişi) --------------------------------
    def _build_management_panel(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 18, 18, 18)

        group = QGroupBox("Yeni Kayıt Ekle")
        form = QFormLayout(group)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Dönem girişi (serbest metin; "2025-2026" formatında).
        self.m_donem = QLineEdit()
        self.m_donem.setPlaceholderText("Örn: 2025-2026")

        # Okul seçimi: birden fazla okul aynı anda seçilebilsin diye checkbox grubu.
        self.m_okul_checks = {}
        okul_widget = self._build_checkbox_group(OKULLAR, self.m_okul_checks)

        # Seviye seçimi (sıra: LH, 9, 10, 11, 12); birden fazla seviye seçilebilir.
        self.m_seviye_checks = {}
        seviye_widget = self._build_checkbox_group(SEVIYELER, self.m_seviye_checks)

        # Etkinlik / Program adı
        self.m_etkinlik = QLineEdit()
        self.m_etkinlik.setPlaceholderText("Örn: Siemens AI Certificate Program")

        # Dosya ekleri: seçilenler önce sadece listelenir, "Kaydet"e basıldığında
        # paylaşılan klasöre kopyalanır.
        self.m_dosyalar = []          # [(dosya_adi, kaynak_yol, boyut)]
        dosya_widget = self._build_file_picker()

        form.addRow("Dönem:", self.m_donem)
        form.addRow("Okul:", okul_widget)
        form.addRow("Seviye:", seviye_widget)
        form.addRow("Program Adı:", self.m_etkinlik)
        form.addRow("Dosyalar:", dosya_widget)

        save_btn = QPushButton("Veritabanına Kaydet")
        save_btn.clicked.connect(self._on_save_activity)
        form.addRow("", save_btn)

        outer.addWidget(group)
        outer.addStretch()
        return page

    # ----- B) Retrospective Query Panel -------------------------------------
    def _build_query_panel(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)

        # Filtre alanı
        filter_box = QGroupBox("Listele")
        flay = QHBoxLayout(filter_box)
        flay.setSpacing(14)

        self.q_donem = QComboBox()
        self.q_donem.setEditable(True)  # kayıtlı dönem yoksa elle de girilebilir
        self.q_okul = QComboBox()
        self.q_okul.addItem("Seçiniz")
        self.q_okul.addItems(OKULLAR)
        self.q_seviye = QComboBox()
        self.q_seviye.addItem("Seçiniz")
        self.q_seviye.addItems(SEVIYELER)

        flay.addWidget(self._labeled("Dönem Seç", self.q_donem))
        flay.addWidget(self._labeled("Okul Seç", self.q_okul))
        flay.addWidget(self._labeled("Seviye Seç", self.q_seviye))

        gen_btn = QPushButton("Listele")
        gen_btn.clicked.connect(self._on_generate_report)
        flay.addWidget(self._labeled(" ", gen_btn))

        outer.addWidget(filter_box)

        # Sonuç tablosu (son sütun: satır bazlı "Sil" butonu)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Dönem", "Okul", "Seviye", "Kurumsal Sertifika Programı",
             "Dosyalar", "İşlem"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        for col in (0, 1, 2, 4, 5):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.verticalHeader().setVisible(False)
        outer.addWidget(self.table)

        # Dışa aktarılacak veri, tablodaki widget'lardan okunmak yerine son
        # üretilen rapor satırlarından alınır.
        self.son_rapor = []
        self.son_filtre = ()          # (donem, okul, seviye)

        actions = QHBoxLayout()
        export_btn = QPushButton("Export to Excel / CSV")
        export_btn.setObjectName("SecondaryBtn")
        export_btn.clicked.connect(self._on_export_report)

        print_btn = QPushButton("Print Report")
        print_btn.setObjectName("GhostBtn")
        print_btn.clicked.connect(self._on_print_report)

        actions.addStretch()
        actions.addWidget(export_btn)
        actions.addWidget(print_btn)
        outer.addLayout(actions)

        return page

    # ----- Yardımcı: dosya yükleme bölümü -----------------------------------
    def _build_file_picker(self):
        """
        Kayıt formunun dosya yükleme bölümünü kurar: seçilen dosyaların listesi
        ile "Dosya Seç" / "Listeden Çıkar" butonları.
        """
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.m_dosya_listesi = QListWidget()
        self.m_dosya_listesi.setMaximumHeight(110)
        self.m_dosya_listesi.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )

        btns = QHBoxLayout()
        btns.setSpacing(8)
        ekle_btn = QPushButton("Dosya Seç...")
        ekle_btn.setObjectName("SecondaryBtn")
        ekle_btn.clicked.connect(self._on_pick_files)
        cikar_btn = QPushButton("Listeden Çıkar")
        cikar_btn.setObjectName("GhostBtn")
        cikar_btn.clicked.connect(self._on_remove_picked_files)
        btns.addWidget(ekle_btn)
        btns.addWidget(cikar_btn)
        btns.addStretch()

        self.m_dosya_bilgi = QLabel()
        self.m_dosya_bilgi.setStyleSheet("color:#7b8794; font-size:12px;")

        lay.addWidget(self.m_dosya_listesi)
        lay.addLayout(btns)
        lay.addWidget(self.m_dosya_bilgi)

        self._refresh_picked_files()
        return wrap

    # ----- Yardımcı: çoktan seçmeli checkbox grubu --------------------------
    @staticmethod
    def _build_checkbox_group(options, target_dict):
        """
        Verilen seçenekler için yatay bir checkbox grubu oluşturur ve her
        checkbox'ı target_dict içine (seçenek adı -> QCheckBox) kaydeder.
        Böylece aynı anda birden fazla seçenek işaretlenebilir.
        """
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        for option in options:
            cb = QCheckBox(option)
            target_dict[option] = cb
            lay.addWidget(cb)
        lay.addStretch()
        return wrap

    # ----- Yardımcı: etiketli dikey sarmalayıcı -----------------------------
    @staticmethod
    def _labeled(text, widget):
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight:600; color:#52606d;")
        lay.addWidget(lbl)
        lay.addWidget(widget)
        return wrap

    # =====================================================================
    # OLAY (EVENT) İŞLEYİCİLERİ
    # =====================================================================

    def _on_pick_files(self):
        """Dosya seçme penceresini açar ve seçilenleri listeye alır."""
        yollar, _ = QFileDialog.getOpenFileNames(
            self, "Kayda Eklenecek Dosyaları Seçin", "", DOSYA_FILTRESI
        )
        if not yollar:
            return

        mevcut_adlar = {ad for ad, _, _ in self.m_dosyalar}
        for yol in yollar:
            ad = os.path.basename(yol)
            if ad in mevcut_adlar:
                continue                     # aynı dosya iki kez eklenmesin

            # Filtre pencerede seçilebilecekleri sınırlar ama kullanıcı dosya
            # adını elle de yazabildiğinden tür burada ayrıca doğrulanır.
            if not uzanti_izinli(ad):
                QMessageBox.warning(
                    self, "Desteklenmeyen Dosya Türü",
                    f"'{ad}' eklenemedi.\n\n"
                    f"Yalnızca şu türler yüklenebilir:\n{IZINLI_TURLER_METNI}",
                )
                continue

            try:
                boyut = os.path.getsize(yol)
            except OSError as exc:
                QMessageBox.warning(
                    self, "Dosya Okunamadı", f"'{ad}' okunamadı:\n{exc}"
                )
                continue

            if boyut > MAX_DOSYA_BOYUTU:
                QMessageBox.warning(
                    self, "Dosya Çok Büyük",
                    f"'{ad}' ({boyut_metni(boyut)}) eklenemedi.\n"
                    f"Tek bir dosya en fazla {boyut_metni(MAX_DOSYA_BOYUTU)} "
                    f"olabilir.",
                )
                continue

            self.m_dosyalar.append((ad, yol, boyut))
            mevcut_adlar.add(ad)

        self._refresh_picked_files()

    def _on_remove_picked_files(self):
        """Kaydetmeden önce, seçili dosyaları listeden çıkarır."""
        secili = self.m_dosya_listesi.selectedIndexes()
        if not secili:
            QMessageBox.information(
                self, "Seçim Yok", "Lütfen listeden çıkarmak istediğiniz dosyaları seçin."
            )
            return
        for idx in sorted((i.row() for i in secili), reverse=True):
            if idx < len(self.m_dosyalar):
                del self.m_dosyalar[idx]
        self._refresh_picked_files()

    def _refresh_picked_files(self):
        """Seçili dosya listesini ve altındaki özet bilgisini tazeler."""
        self.m_dosya_listesi.clear()
        for ad, _yol, boyut in self.m_dosyalar:
            self.m_dosya_listesi.addItem(f"{ad}    •    {boyut_metni(boyut)}")

        if not self.m_dosyalar:
            self.m_dosya_bilgi.setText(
                f"Dosya seçilmedi (isteğe bağlı) • İzin verilen türler: "
                f"{IZINLI_TURLER_METNI} • Dosya başına en fazla "
                f"{boyut_metni(MAX_DOSYA_BOYUTU)}"
            )
        else:
            toplam = sum(boyut for _, _, boyut in self.m_dosyalar)
            self.m_dosya_bilgi.setText(
                f"{len(self.m_dosyalar)} dosya seçildi • toplam "
                f"{boyut_metni(toplam)} • kaydedince paylaşılan klasöre kopyalanır"
            )

    def _on_save_activity(self):
        """Management Panel formundaki kaydı veritabanına yazar."""
        donem = self.m_donem.text().strip()
        secili_okullar = [ad for ad, cb in self.m_okul_checks.items() if cb.isChecked()]
        secili_seviyeler = [ad for ad, cb in self.m_seviye_checks.items() if cb.isChecked()]
        etkinlik = self.m_etkinlik.text().strip()

        # Basit doğrulama
        if not donem or not etkinlik:
            QMessageBox.warning(
                self, "Eksik Bilgi",
                "Lütfen 'Dönem' ve 'Program Adı' alanlarını doldurun.",
            )
            return

        if not secili_okullar or not secili_seviyeler:
            QMessageBox.warning(
                self, "Eksik Bilgi",
                "Lütfen en az bir 'Okul' ve bir 'Seviye' seçin.",
            )
            return

        if "-" not in donem:
            QMessageBox.warning(
                self, "Geçersiz Dönem",
                "Dönem 'YYYY-YYYY' formatında olmalıdır. Örn: 2025-2026",
            )
            return

        # Önce dosyalar paylaşılan klasöre kopyalanır: klasöre erişilemiyorsa
        # veritabanına hiçbir şey yazılmasın, yarım kayıt oluşmasın.
        kopyalanan = []          # [(dosya_adi, saklanan_ad, boyut)]
        try:
            for ad, yol, boyut in self.m_dosyalar:
                saklanan_ad = saklama_adi_uret(ad)
                depoya_kopyala(yol, saklanan_ad)
                kopyalanan.append((ad, saklanan_ad, boyut))
        except OSError as exc:
            depodan_sil([s for _, s, _ in kopyalanan])
            QMessageBox.critical(
                self, "Dosya Kopyalanamadı",
                f"Dosyalar paylaşılan klasöre kopyalanamadı:\n\n"
                f"{DOSYA_KLASORU}\n\n{exc}\n\n"
                "Kayıt oluşturulmadı. Klasöre erişiminizi kontrol edin.",
            )
            return

        # Seçilen her okul x seviye kombinasyonu için ayrı bir kayıt oluşturulur.
        try:
            yeni_idler = []
            for okul in secili_okullar:
                for seviye in secili_seviyeler:
                    yeni_idler.append(
                        self.db.add_activity(donem, okul, seviye, etkinlik)
                    )

            # Dosya klasöre bir kez kopyalanır ve oluşan tüm kayıtlara bağlanır;
            # her kombinasyon için ayrı bir kopya oluşturulmaz.
            for ad, saklanan_ad, boyut in kopyalanan:
                file_id = self.db.add_file(ad, saklanan_ad, boyut)
                for activity_id in yeni_idler:
                    self.db.link_file(activity_id, file_id)
        except pymssql.Error as exc:
            # Veritabanı yazımı başarısızsa klasöre atılan kopyalar geri alınır.
            depodan_sil([s for _, s, _ in kopyalanan])
            QMessageBox.critical(self, "Veritabanı Hatası", str(exc))
            return

        kombinasyonlar = "\n".join(
            f"{okul} • {seviye}"
            for okul in secili_okullar
            for seviye in secili_seviyeler
        )
        dosya_notu = (
            f"\n\n{len(self.m_dosyalar)} dosya eklendi."
            if self.m_dosyalar else ""
        )
        QMessageBox.information(
            self, "Kayıt Başarılı",
            f"Program kaydedildi:\n\n{donem}\n{kombinasyonlar}\n{etkinlik}"
            f"{dosya_notu}",
        )

        # Formu temizle ve dönem combobox'larını tazele.
        self.m_etkinlik.clear()
        self.m_donem.clear()
        for cb in self.m_okul_checks.values():
            cb.setChecked(False)
        for cb in self.m_seviye_checks.values():
            cb.setChecked(False)
        self.m_dosyalar.clear()
        self._refresh_picked_files()
        self._refresh_donem_combos()
        self.statusBar().showMessage(f"Kaydedildi: {etkinlik} ({donem})")

    def _on_delete_result_row(self, activity_id, donem, okul, seviye, etkinlik):
        """
        Listeleme (Retrospective) tablosundaki bir satırın yanındaki "Sil"
        butonuna basıldığında, onay alarak ilgili kaydı veritabanından siler
        ve raporu aynı filtrelerle yeniden üretir.
        """
        cevap = QMessageBox.question(
            self, "Kaydı Sil",
            f"Bu kayıt silinsin mi?\n\n{donem} • {okul} • {seviye}\n{etkinlik}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if cevap != QMessageBox.StandardButton.Yes:
            return

        try:
            self.db.delete_activity(activity_id)
        except pymssql.Error as exc:
            QMessageBox.critical(self, "Veritabanı Hatası", str(exc))
            return

        self._refresh_donem_combos()
        self.statusBar().showMessage(f"Silindi: {etkinlik} ({donem})")
        self._on_generate_report()

    def _on_generate_report(self):
        """Retrospective tracking algoritmasını çalıştırıp tabloyu doldurur."""
        donem = self.q_donem.currentText().strip()
        okul = self.q_okul.currentText()
        seviye = self.q_seviye.currentText()

        if not donem:
            QMessageBox.warning(
                self, "Dönem Seçilmedi",
                "Lütfen sorgulamak için bir dönem seçin veya girin.",
            )
            return

        if okul == "Seçiniz" or seviye == "Seçiniz":
            QMessageBox.warning(
                self, "Eksik Bilgi",
                "Lütfen 'Okul' ve 'Seviye' alanlarından bir seçim yapın.",
            )
            return

        try:
            rows = generate_retrospective(self.db, donem, okul, seviye)
        except pymssql.Error as exc:
            QMessageBox.critical(self, "Veritabanı Hatası", str(exc))
            return

        self.son_rapor = rows
        self.son_filtre = (donem, okul, seviye)

        self.table.setRowCount(0)
        for r in rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            values = [
                r["donem"],
                r["okul"],
                r["seviye"],
                r["etkinlik"],
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if col < 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, item)

            # Gerçek bir kayda karşılık gelen satırlara "Sil" butonu eklenir;
            # "Kayıt bulunamadı" satırlarında (id=None) silinecek bir şey yoktur.
            if r["id"] is not None:
                if r["dosya_sayisi"]:
                    dosya_btn = QPushButton(f"Dosyalar ({r['dosya_sayisi']})")
                    dosya_btn.setObjectName("SecondaryBtn")
                    dosya_btn.clicked.connect(
                        lambda _checked=False, r=r: self._on_show_files(r)
                    )
                    self.table.setCellWidget(row_idx, 4, dosya_btn)
                else:
                    bos = QTableWidgetItem("—")
                    bos.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(row_idx, 4, bos)

                sil_btn = QPushButton("Sil")
                sil_btn.setObjectName("GhostBtn")
                sil_btn.clicked.connect(
                    lambda _checked=False, r=r: self._on_delete_result_row(
                        r["id"], r["donem"], r["okul"], r["seviye"], r["etkinlik"]
                    )
                )
                self.table.setCellWidget(row_idx, 5, sil_btn)

        self.statusBar().showMessage(
            f"Rapor üretildi: {len(rows)} aşama tarandı "
            f"({donem} / {okul} / {seviye})"
        )

    def _on_show_files(self, r):
        """Rapor satırındaki kayda ekli dosyaları gösteren pencereyi açar."""
        dlg = EkDosyalarDialog(
            self, self.db, r["id"],
            f"{r['donem']} • {r['okul']} • {r['seviye']} — {r['etkinlik']}",
        )
        dlg.exec()
        if dlg.degisti:
            # Ek silindiyse satırdaki dosya sayısı güncellensin.
            self._on_generate_report()

    # ----- Dışa aktarma -----------------------------------------------------
    EXPORT_BASLIKLARI = [
        "Dönem", "Okul", "Seviye", "Kurumsal Sertifika Programı", "Dosya Sayısı",
    ]

    def _export_satirlari(self):
        """Son üretilen raporu, CSV'ye yazılacak satır listesine dönüştürür."""
        satirlar = []
        for r in self.son_rapor:
            satirlar.append([
                r["donem"],
                r["okul"],
                r["seviye"],
                r["etkinlik"],
                # Placeholder satırlarda dosya sayısı 0'dır; tabloda "—" gösterilir.
                r["dosya_sayisi"] if r["id"] is not None else "",
            ])
        return satirlar

    def _varsayilan_export_adi(self):
        """Kaydetme penceresine önerilecek dosya adını üretir."""
        donem, okul, seviye = self.son_filtre or ("", "", "")
        parcalar = [p for p in ("Rapor", donem, okul, seviye) if p]
        ad = "_".join(parcalar) + f"_{datetime.now():%Y%m%d_%H%M}.csv"
        # Windows'ta dosya adında kullanılamayan karakterler temizlenir.
        return re.sub(r'[\\/:*?"<>|]', "-", ad)

    def _on_export_report(self):
        """
        Listeleme tablosundaki raporu, Excel'in doğrudan açabildiği bir CSV
        dosyasına aktarır. Türkçe karakterler için UTF-8 BOM, Türkçe Excel'in
        sütunları ayırabilmesi için ';' ayırıcı kullanılır.
        """
        if not self.son_rapor:
            QMessageBox.information(
                self, "Aktarılacak Kayıt Yok",
                "Önce 'Listele' butonuyla bir rapor üretin.",
            )
            return

        hedef, _ = QFileDialog.getSaveFileName(
            self, "Raporu Dışa Aktar",
            self._varsayilan_export_adi(),
            "CSV Dosyası (*.csv)",
        )
        if not hedef:
            return
        if not hedef.lower().endswith(".csv"):
            hedef += ".csv"

        donem, okul, seviye = self.son_filtre or ("", "", "")
        try:
            # newline="" olmadan csv modülü Windows'ta satır aralarına fazladan
            # boş satır yazar. utf-8-sig, Excel'in kodlamayı tanıması içindir.
            with open(hedef, "w", newline="", encoding="utf-8-sig") as f:
                yazici = csv.writer(f, delimiter=";")
                yazici.writerow(["Kurumsal Sertifika Programı Raporu"])
                yazici.writerow([f"Dönem: {donem}", f"Okul: {okul}",
                                 f"Seviye: {seviye}"])
                yazici.writerow([f"Oluşturulma: {datetime.now():%d.%m.%Y %H:%M}"])
                yazici.writerow([])
                yazici.writerow(self.EXPORT_BASLIKLARI)
                yazici.writerows(self._export_satirlari())
        except OSError as exc:
            # Dosya başka bir programda (çoğunlukla Excel'de) açıksa
            # PermissionError gelir; o da bir OSError'dır.
            QMessageBox.critical(
                self, "Dışa Aktarılamadı",
                f"Dosya yazılamadı:\n{hedef}\n\n{exc}\n\n"
                "Dosya Excel'de açıksa kapatıp tekrar deneyin.",
            )
            return

        self.statusBar().showMessage(f"Rapor dışa aktarıldı: {hedef}")
        cevap = QMessageBox.question(
            self, "Dışa Aktarıldı",
            f"Rapor kaydedildi:\n{hedef}\n\nDosya şimdi açılsın mı?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if cevap == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(hedef))

    # ----- Yazdırma ---------------------------------------------------------
    def _rapor_html(self):
        """
        Son üretilen raporu, yazdırma için HTML'e dönüştürür. Qt'nin zengin
        metin motoru CSS'in sınırlı bir alt kümesini desteklediğinden stiller
        satır içi tutulur.
        """
        donem, okul, seviye = self.son_filtre or ("", "", "")

        satirlar = []
        for r in self.son_rapor:
            # Placeholder satırlar (id=None) griye çalar; tabloda "—" gösterilir.
            bulundu = r["id"] is not None
            renk = "#1d3557" if bulundu else "#98a2b3"
            dosya = str(r["dosya_sayisi"]) if bulundu else "—"
            hucreler = "".join(
                f'<td align="center" style="color:{renk};">{escape(str(v))}</td>'
                for v in (r["donem"], r["okul"], r["seviye"])
            )
            satirlar.append(
                f"<tr>{hucreler}"
                f'<td style="color:{renk};">{escape(str(r["etkinlik"]))}</td>'
                f'<td align="center" style="color:{renk};">{dosya}</td></tr>'
            )

        basliklar = "".join(
            f'<th align="center" bgcolor="#e8eef6">{escape(b)}</th>'
            for b in self.EXPORT_BASLIKLARI
        )
        return f"""
        <html><body style="font-family:Segoe UI, Arial; font-size:10pt;">
          <h2 style="color:#1d3557; margin-bottom:2px;">
            Kurumsal Sertifika Programı Raporu
          </h2>
          <p style="color:#4a5568; margin-top:0;">
            <b>Dönem:</b> {escape(donem)} &nbsp;&nbsp;
            <b>Okul:</b> {escape(okul)} &nbsp;&nbsp;
            <b>Seviye:</b> {escape(seviye)}<br/>
            <b>Oluşturulma:</b> {datetime.now():%d.%m.%Y %H:%M}
          </p>
          <table width="100%" cellspacing="0" cellpadding="6" border="1"
                 style="border-color:#c6d0dd;">
            <tr>{basliklar}</tr>
            {''.join(satirlar)}
          </table>
          <p style="color:#98a2b3; font-size:8pt;">
            Toplam {len(self.son_rapor)} aşama tarandı.
          </p>
        </body></html>
        """

    def _on_print_report(self):
        """Listeleme tablosundaki raporu baskı önizlemesiyle yazdırır."""
        if not self.son_rapor:
            QMessageBox.information(
                self, "Yazdırılacak Kayıt Yok",
                "Önce 'Listele' butonuyla bir rapor üretin.",
            )
            return

        if not QPrinterInfo.availablePrinterNames():
            QMessageBox.warning(
                self, "Yazıcı Bulunamadı",
                "Bu bilgisayarda tanımlı bir yazıcı yok.\n\n"
                "Bir yazıcı ekleyin ya da raporu 'Export to Excel / CSV' "
                "ile dışa aktarın.",
            )
            return

        belge = QTextDocument()
        belge.setHtml(self._rapor_html())

        yazici = QPrinter(QPrinter.PrinterMode.HighResolution)
        yazici.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        yazici.setPageOrientation(QPageLayout.Orientation.Portrait)
        donem, okul, seviye = self.son_filtre or ("", "", "")
        yazici.setDocName(f"Rapor {donem} {okul} {seviye}".strip())

        onizleme = QPrintPreviewDialog(yazici, self)
        onizleme.setWindowTitle("Rapor Önizleme")
        onizleme.resize(900, 650)
        # Önizleme her sayfa çizimi istediğinde belge yeniden basılır.
        onizleme.paintRequested.connect(belge.print)
        onizleme.exec()

    # =====================================================================
    # YARDIMCI METOTLAR
    # =====================================================================

    def _refresh_donem_combos(self):
        """Sorgulama panelindeki dönem combobox'ını DB'deki dönemlerle günceller."""
        mevcut = self.q_donem.currentText()
        try:
            donemler = self.db.distinct_donemler()
        except pymssql.Error as exc:
            # Sunucuya erişilemiyorsa uygulama çökmemeli; combobox mevcut
            # içeriğiyle kalır, durum çubuğunda uyarı gösterilir.
            self.statusBar().showMessage(f"Dönem listesi alınamadı: {exc}")
            return
        self.q_donem.clear()
        self.q_donem.addItems(donemler)
        if mevcut:
            self.q_donem.setCurrentText(mevcut)



# ---------------------------------------------------------------------------
# UYGULAMA GİRİŞ NOKTASI
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(CORPORATE_QSS)
    app.setFont(QFont("Segoe UI", 10))

    # MainWindow yapıcısı ilk MSSQL bağlantısını kurar (şema kontrolü). Sunucu
    # kapalı/erişilemez durumdaysa çıplak bir traceback yerine anlaşılır bir
    # uyarı gösterilir.
    try:
        window = MainWindow()
    except pymssql.Error as exc:
        QMessageBox.critical(
            None, "Veritabanına Bağlanılamadı",
            f"{DB_NAME} ({DB_SERVER}) veritabanına bağlanılamadı.\n\n"
            f"{exc}\n\n"
            "Bu makinenin internet erişimini ve 1433 numaralı portun "
            "güvenlik duvarı tarafından engellenmediğini kontrol edin.",
        )
        sys.exit(1)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
