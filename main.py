# -*- coding: utf-8 -*-
"""
Kurumsal İletişim Sertifika Programı
========================================================
Okulun "Kurumsal İletişim (Corporate Communications)" birimi için geliştirilmiş,
kurumsal sertifika programlarını (Siemens, Cervantes, Özyeğin vb.) takip eden
modern bir masaüstü uygulamasıdır.

Tek dosyada hem SQLite veri yönetimini hem de PyQt6 arayüzünü birleştirir.

Bağımlılık:
    pip install PyQt6
"""

import sys
import sqlite3
import ctypes
from contextlib import closing

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QGroupBox, QFrame,
    QAbstractItemView, QStatusBar,
)

# ---------------------------------------------------------------------------
# SABİTLER (Domain kuralları)
# ---------------------------------------------------------------------------

DB_NAME = "corporate_certificates.db"

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


# ---------------------------------------------------------------------------
# VERİTABANI KATMANI (SQLite)
# ---------------------------------------------------------------------------

class Database:
    """Tüm SQLite işlemlerini yöneten yardımcı sınıf."""

    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self._init_schema()

    def _connect(self):
        """Veritabanına bağlantı açar (her işlem için yeni bağlantı)."""
        return sqlite3.connect(self.db_name)

    def _init_schema(self):
        """activities tablosunu (yoksa) oluşturur."""
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    donem         TEXT NOT NULL,   -- Örn: "2025-2026"
                    okul          TEXT NOT NULL,   -- "FENLI" / "KOLEJ"
                    seviye        TEXT NOT NULL,   -- "LH","9","10","11","12"
                    etkinlik_adi  TEXT NOT NULL    -- Örn: "Siemens AI Certificate Program"
                )
                """
            )
            conn.commit()

    def add_activity(self, donem, okul, seviye, etkinlik_adi):
        """Yeni bir kurumsal sertifika kaydı ekler."""
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO activities (donem, okul, seviye, etkinlik_adi) "
                "VALUES (?, ?, ?, ?)",
                (donem, okul, seviye, etkinlik_adi),
            )
            conn.commit()

    def find_activities(self, donem, okul, seviye):
        """
        Belirli dönem/okul/seviye için kayıtlı (id, etkinlik_adi) çiftlerini döndürür.
        Aynı kombinasyonda birden fazla kayıt olabileceğinden liste döner.
        """
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id, etkinlik_adi FROM activities "
                "WHERE donem = ? AND okul = ? AND seviye = ?",
                (donem, okul, seviye),
            )
            return cur.fetchall()

    def distinct_donemler(self):
        """Veritabanında kayıtlı tüm dönemleri (azalan sırada) döndürür."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT DISTINCT donem FROM activities ORDER BY donem DESC"
            )
            return [row[0] for row in cur.fetchall()]

    def get_all_activities(self):
        """
        Tüm kayıtları (id dahil) en yeni dönem üstte olacak şekilde döndürür.
        Silme işlemi için id bilgisine ihtiyaç duyulur.
        """
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id, donem, okul, seviye, etkinlik_adi FROM activities "
                "ORDER BY donem DESC, okul, seviye"
            )
            return cur.fetchall()

    def delete_activity(self, activity_id):
        """Verilen id'ye sahip kaydı veritabanından siler."""
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
            conn.commit()


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
            for activity_id, ad in etkinlikler:
                sonuclar.append({
                    "id": activity_id,
                    "asama": asama,
                    "donem": mevcut_donem,
                    "okul": okul,
                    "seviye": mevcut_seviye,
                    "etkinlik": ad,
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
        self.statusBar().showMessage("Hazır • Veritabanı: " + DB_NAME)

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

        # Okul seçimi (ilk seçenek "Seçiniz" placeholder'ıdır, gerçek değer değildir).
        self.m_okul = QComboBox()
        self.m_okul.addItem("Seçiniz")
        self.m_okul.addItems(OKULLAR)

        # Seviye seçimi (görsel sıra: LH, 9, 10, 11, 12). İlk seçenek placeholder'dır.
        self.m_seviye = QComboBox()
        self.m_seviye.addItem("Seçiniz")
        self.m_seviye.addItems(SEVIYELER)

        # Etkinlik / Program adı
        self.m_etkinlik = QLineEdit()
        self.m_etkinlik.setPlaceholderText("Örn: Siemens AI Certificate Program")

        form.addRow("Dönem:", self.m_donem)
        form.addRow("Okul:", self.m_okul)
        form.addRow("Seviye:", self.m_seviye)
        form.addRow("Program Adı:", self.m_etkinlik)

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
            ["Aşama", "Dönem", "Okul", "Seviye", "Kurumsal Sertifika Programı", "İşlem"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        for col in range(4):
            self.table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.verticalHeader().setVisible(False)
        outer.addWidget(self.table)

        # Dışa aktarma / yazdırma buton şablonları (ileride doldurulacak)
        actions = QHBoxLayout()
        export_btn = QPushButton("Export to Excel / CSV")
        export_btn.setObjectName("SecondaryBtn")
        export_btn.clicked.connect(self._on_export_placeholder)

        print_btn = QPushButton("Print Report")
        print_btn.setObjectName("GhostBtn")
        print_btn.clicked.connect(self._on_print_placeholder)

        actions.addStretch()
        actions.addWidget(export_btn)
        actions.addWidget(print_btn)
        outer.addLayout(actions)

        return page

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

    def _on_save_activity(self):
        """Management Panel formundaki kaydı veritabanına yazar."""
        donem = self.m_donem.text().strip()
        okul = self.m_okul.currentText()
        seviye = self.m_seviye.currentText()
        etkinlik = self.m_etkinlik.text().strip()

        # Basit doğrulama
        if not donem or not etkinlik:
            QMessageBox.warning(
                self, "Eksik Bilgi",
                "Lütfen 'Dönem' ve 'Program Adı' alanlarını doldurun.",
            )
            return

        if okul == "Seçiniz" or seviye == "Seçiniz":
            QMessageBox.warning(
                self, "Eksik Bilgi",
                "Lütfen 'Okul' ve 'Seviye' alanlarından bir seçim yapın.",
            )
            return

        if "-" not in donem:
            QMessageBox.warning(
                self, "Geçersiz Dönem",
                "Dönem 'YYYY-YYYY' formatında olmalıdır. Örn: 2025-2026",
            )
            return

        try:
            self.db.add_activity(donem, okul, seviye, etkinlik)
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Veritabanı Hatası", str(exc))
            return

        QMessageBox.information(
            self, "Kayıt Başarılı",
            f"Program kaydedildi:\n\n{donem} • {okul} • {seviye}\n{etkinlik}",
        )

        # Formu temizle ve dönem combobox'larını tazele.
        self.m_etkinlik.clear()
        self.m_donem.clear()
        self.m_okul.setCurrentText("Seçiniz")
        self.m_seviye.setCurrentText("Seçiniz")
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
        except sqlite3.Error as exc:
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

        rows = generate_retrospective(self.db, donem, okul, seviye)

        self.table.setRowCount(0)
        for r in rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            values = [
                f"Aşama {r['asama']}",
                r["donem"],
                r["okul"],
                r["seviye"],
                r["etkinlik"],
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if col < 4:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col, item)

            # Gerçek bir kayda karşılık gelen satırlara "Sil" butonu eklenir;
            # "Kayıt bulunamadı" satırlarında (id=None) silinecek bir şey yoktur.
            if r["id"] is not None:
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

    def _on_export_placeholder(self):
        """İleride Excel/CSV dışa aktarma kodu buraya gelecek."""
        QMessageBox.information(
            self, "Export (Şablon)",
            "Excel/CSV dışa aktarma işlevi bu sürümde şablon olarak bırakılmıştır.\n"
            "Buraya pandas/openpyxl tabanlı dışa aktarma kodu eklenebilir.",
        )

    def _on_print_placeholder(self):
        """İleride QPrinter tabanlı yazdırma kodu buraya gelecek."""
        QMessageBox.information(
            self, "Print (Şablon)",
            "Yazdırma işlevi bu sürümde şablon olarak bırakılmıştır.\n"
            "Buraya QPrinter / QPrintDialog tabanlı yazdırma kodu eklenebilir.",
        )

    # =====================================================================
    # YARDIMCI METOTLAR
    # =====================================================================

    def _refresh_donem_combos(self):
        """Sorgulama panelindeki dönem combobox'ını DB'deki dönemlerle günceller."""
        mevcut = self.q_donem.currentText()
        donemler = self.db.distinct_donemler()
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

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
