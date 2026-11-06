# MIMARI.md — CorporateCertificate

Kurumsal İletişim birimi için, kurumsal sertifika programlarını (Siemens, Cervantes, Özyeğin vb.) dönem, okul ve seviye bazında takip eden tek dosyalık **PyQt6** masaüstü uygulaması. Veriler merkezî bir **SQL Server 2022** veritabanında (`CorporateCertificate`), dosya ekleri paylaşılan ağ klasöründe durur. UI metinleri ve kod yorumları Türkçedir.

## AGENTS.md'den sapmalar

AGENTS.md .NET/Blazor projeleri için yazılmıştır; bu proje Python masaüstü uygulamasıdır. Ortak kuralların (§1, §2, §8–§10, §13–§16 ve kök/docs düzeni) hepsi geçerlidir; teknolojiye bağlı olanlar şöyle uyarlanır:

| AGENTS.md | Bu projede | Gerekçe |
|---|---|---|
| §3–§4 .NET solution, `src/<App>.Web/UI/Shared` | `src/main.py` tek dosya; katmanlar yorum başlıklarıyla ayrılır | Küçük, tek ekranlı masaüstü aracı; çok projeli yapı gereksiz karmaşıklık olur (YAGNI). |
| §4 kökte `Directory.Packages.props` | Kökte `requirements.txt` (sürümler sabit) | Python karşılığı; `pip install -r requirements.txt` kökten çalışır. |
| §4 kökte başka klasör yok | `.vscode/` (launch/settings) ve yerel `.venv/` kökte | `.vscode` F5 hata ayıklama yapılandırmasıdır; `.venv` git'e girmez. |
| §4 `docs/iis-yayini.md` | `docs/dagitim.md` | IIS yok; tek dosyalık exe olarak dağıtılır. |
| §5/§6 İngilizce tablo/kolon adları, `int Id` | Kolonlar Türkçe (`donem`, `okul`, `seviye`, …) | **Production şeması yetkilidir (§9.1)**; yeniden adlandırma production'da şema değişikliği gerektirir. |
| §5 kalıcı zaman UTC | `dbo.files.yuklenme_tarihi` = `SYSDATETIME()` (sunucu yerel saati) | Aynı nedenle; değiştirilecekse script hazırlanır, insan uygular. |
| §6 EF Core | `pymssql` + elle yazılmış, parametreli (`%s`) SQL | Python; ORM gerekmeyecek kadar küçük. |
| §7, §11, §12 Blazor/API/SignalR | Uygulanmaz | API sunulmuyor, dış API tüketilmiyor; UI PyQt6. |
| §9.5 local DB | **Local/test DB yok — tek ortam production** | Uygulamayı çalıştırmak production'a bağlanır. Test için ayrı DB istenirse `CORPCERT_DB` + `CORPCERT_INIT_SCHEMA=1` ile kurulabilir. |
| §10 auth / fallback policy | Uygulama içi kimlik doğrulama yok; tek ortak SQL login | Kurum içi araç. Login **en az yetkili** olmalıdır (aşağıda "Bilinen riskler"). |
| §15 `dotnet build/test`, xUnit | `python -m py_compile src/main.py`, `python -m unittest discover -s tests` | Python karşılıkları; testler DB'ye ve ağ klasörüne dokunmaz. |
| §14 `dev`/`main`, GitLab | Remote şu an GitHub (`origin`) | GitLab'a taşınması `MarkdownSourceFile/gitlab.md`'ye göre yapılır. |

## Komutlar

```bash
# Bağımlılıklar (kökten, .venv etkin)
pip install -r requirements.txt

# Doğrulama — DB'ye bağlanmaz
python -m py_compile src/main.py
python -m unittest discover -s tests

# Uygulamayı çalıştır — DİKKAT: production DB'ye bağlanır (src/corpcert.ini gerekir)
python src/main.py

# Exe derle (çıktı: dist/CorporateCertificate.exe; build/ dist/ git'e girmez)
pyinstaller --noconfirm --clean docs/CorporateCertificate.spec
```

VS Code'da F5: `.vscode/launch.json` → "Kurumsal Sertifika (main.py)".

## Klasör düzeni

```text
CorporateCertificate/
├── .gitattributes / .gitignore
├── AGENTS.md / CLAUDE.md
├── requirements.txt
├── .vscode/                     # launch.json, settings.json
├── docs/
│   ├── MIMARI.md                # bu dosya
│   ├── dagitim.md               # derleme, dağıtım, yapılandırma, şema
│   ├── schema.sql               # MSSQL şeması (idempotent)
│   ├── corpcert.ini.example     # yapılandırma şablonu (secret içermez)
│   └── CorporateCertificate.spec  # PyInstaller onefile spec
├── src/main.py
└── tests/test_main.py
```

Yerelde kalan ve git'e girmeyen: `.venv/`, `build/`, `dist/`, `__pycache__/`, `corpcert.ini`, eski `corporate_certificates.db` (SQLite; artık hiçbir şey okumuyor, yalnızca referans).

## Yapılandırma

Öncelik: **ortam değişkeni > `corpcert.ini` > varsayılan**. `corpcert.ini` exe'nin (geliştirmede `src/main.py`'nin) yanında aranır. Şablon: `docs/corpcert.ini.example`.

| Ortam değişkeni | ini | Varsayılan |
|---|---|---|
| `CORPCERT_SERVER` | `[database] server` | `94.102.74.165` |
| `CORPCERT_DB` | `[database] name` | `CorporateCertificate` |
| `CORPCERT_USER` | `[database] user` | — (zorunlu) |
| `CORPCERT_PASSWORD` | `[database] password` | — (zorunlu) |
| `CORPCERT_INIT_SCHEMA` | `[database] init_schema` | `0` — açılışta DDL **çalışmaz** |
| `CORPCERT_DOSYA_KLASORU` | `[files] folder` | `\\172.16.0.201\Kurumsal_Video\ProgramFiles\CorporateCertificate\dosyalar` |

Kullanıcı/parola eksikse uygulama bağlanmayı denemeden hangi dosyaya ne yazılacağını söyleyip kapanır. Günlük dosyası: `%LOCALAPPDATA%\CorporateCertificate\app.log` (dönen, 3 × 1 MB). Kullanıcıya ham `pymssql` hata metni gösterilmez, ayrıntı buraya yazılır.

## Mimari (`src/main.py`, yukarıdan aşağıya)

1. **Yapılandırma ve günlük** — `ayarlari_yukle`, `gunlugu_kur`, `hata_bildir` (except bloğu içinden çağrılır: log + genel mesaj).
2. **Domain sabitleri** — `OKULLAR`, `SEVIYELER` (`LH, 9, 10, 11, 12`), `ONCEKI_SEVIYE`, `IZINLI_UZANTILAR`, `MAX_DOSYA_BOYUTU` (50 MB), `DONEM_DESENI`.
3. **`Database`** — pymssql sarmalayıcısı; her işlem kendi bağlantısını açar (`contextlib.closing`). `charset="UTF-8"` Türkçe karakterler için zorunludur. Yer tutucu **`%s`**'dir (`?` değil); SQL içinde düz `%` → `%%`.
   - Açılışta yalnızca `SELECT 1` ile erişim denenir. `DDL_STATEMENTS` (= `docs/schema.sql`, `GO`'suz) yalnızca `init_schema` açıksa çalışır (AGENTS.md §9.1). İkisi senkron tutulmalı ve her ifade idempotent kalmalıdır.
   - Çok satırlı yazımlar **tek transaction**'dır (`_transaction`): `create_activities` (okul × seviye kayıtları + dosya satırları + bağlar) ve `add_files`. Hata olursa hiçbir satır kalmaz.
   - Tablolar: `dbo.activities`, `dbo.files` (yalnızca üstveri), çoka-çok `dbo.activity_files` (`ON DELETE CASCADE`).
4. **Dosya deposu** — `depo_klasoru`, `depo_yolu`, `depoya_kopyala`, `depodan_sil`, `saklama_adi_uret`. Ağ klasörü erişimi bunlardan geçer (tek istisna: kullanılmayan `EkDosyalarDialog._on_save_as`).
5. **Geriye tarama** — `generate_retrospective(db, donem, okul, seviye)`: her adımda bir yıl geri **ve** bir seviye aşağı (`12 → … → 9 → LH`), `LH`'den sonra durur; kayıt yoksa yer tutucu satır (`id=None`) üretir.
6. **UI** — `MainWindow` (sekmeler: "Yeni Kayıt Ekle", "Listele"), `EkDosyalarDialog`, `CORPORATE_QSS`.

### Düzenlemeden önce bilinmesi gerekenler

- **Kayıt sırası:** Dosyalar önce ağ klasörüne kopyalanır, sonra DB transaction'ı çalışır. Klasöre erişilemezse DB'ye hiçbir şey yazılmaz; DB yazımı başarısızsa (transaction geri alındığı için) kopyaların hepsi silinir.
- **Bir dosya, çok kayıt:** 2 okul × 5 seviye kaydı → klasörde tek dosya, `dbo.files`'ta tek satır, 10 bağ.
- `saklama_adi_uret` çakışmasız ad üretir (`2025 Rapor.pdf` → `2025_Rapor_9f3c1ab2.pdf`); özgün ad `dosya_adi`'nda kalır. Özgün adla klasöre yazma.
- **Sahipsiz dosya temizliği:** kayıt/bağ silinince `_sahipsiz_dosyalari_temizle` (`OUTPUT DELETED.saklanan_ad`) DB satırlarını siler, `depodan_sil` fiziksel dosyaları kaldırır. `depodan_sil` klasör hatalarını **loglar ama yükseltmez** — DB'de başarılı olmuş silme başarısız sayılmaz.
- **Dosya doğrulama:** her iki giriş noktası (`_on_pick_files`, `_on_add_files`) `dosya_secimlerini_dogrula`'dan geçer (tür, boyut, aynı ad). Yeni seçiciler de geçmeli.
- **Dönem:** `donem_gecerli` hem kayıtta hem raporda `YYYY-YYYY` ve ardışık yıl denetler (kolon `NVARCHAR(9)`).
- **Export (CSV):** `encoding="utf-8-sig"`, `delimiter=";"`, `newline=""` Türkçe Excel uyumu için kaldırılmamalı. `self.son_rapor`'dan yazılır (tablo hücrelerinde buton var). `EXPORT_BASLIKLARI` CSV ve yazdırmada ortaktır.
- **Yazdırma:** `QTextDocument` + `QPrintPreviewDialog`; Qt rich text CSS'in alt kümesini destekler, stiller satır içi. Yazıcı yoksa CSV'ye yönlendirir.
- **QSS:** `QFrame` arka planı için `WA_StyledBackground` gerekir; `HeaderBar` vb. `setObjectName` değerleridir, sınıf değil.
- **Başlık çubuğu rengi:** `_apply_native_titlebar_color` DWM API (Win11 22000+); diğer sürümlerde sessizce atlanır.
- **pymssql neden (pyodbc değil):** pyodbc makinede "ODBC Driver 18" ister ve PyInstaller bunu paketleyemez; pymssql FreeTDS'i wheel içinde taşır. Dağıtım sorunu çözülmeden pyodbc'ye dönülmez.
- **Ölü kod:** `Database.get_all_activities` ve `EkDosyalarDialog._on_save_as` çağrılmıyor ("Farklı Kaydet" butonu kaldırıldı).

## Bilinen riskler / açık işler

1. **Sızmış `sa` parolası (KRİTİK):** Eski sürümlerde `sa` parolası `main.py` içinde açık yazılıydı; bu dosya **herkese açık GitHub deposunun geçmişinde** ve eski `CorporateCertificate.exe`'lerin içinde duruyor. Parola **sunucu tarafında değiştirilmelidir**; kodu temizlemek tek başına yetmez. Ardından git geçmişinin temizlenmesi (veya deponun private yapılması) değerlendirilmelidir.
2. **`sa` yerine en az yetkili login:** Uygulama yalnızca 3 tabloda `SELECT/INSERT/DELETE` ister; DDL yetkisi gerekmez. Ayrı bir login (örn. `corpcert_app`) açılıp `corpcert.ini`'ye o yazılmalıdır. Masaüstü uygulaması doğrudan DB'ye bağlandığından parola istemci makinede bulunur; risk ancak yetkiyi daraltarak sınırlanabilir.
3. **Sunucu internete açık IP** (`94.102.74.165:1433`): mümkünse yalnızca kurum ağından/VPN'den erişilebilir olmalı.
4. Uygulama içi yetki yok: DB'ye erişebilen herkes her kaydı silebilir.
