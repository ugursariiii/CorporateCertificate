# Dağıtım — CorporateCertificate.exe

> AGENTS.md'deki `iis-yayini.md`'nin bu projedeki karşılığıdır (IIS yok, masaüstü exe).

## 1. Derleme

Kök dizinden, `.venv` etkinken:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests
pyinstaller --noconfirm --clean docs/CorporateCertificate.spec
```

Çıktı tek dosyadır: `dist/CorporateCertificate.exe` (~40 MB, onefile). Python, PyQt6 ve pymssql (FreeTDS) içindedir; hedef makineye ODBC sürücüsü veya Python kurulmaz. `build/` ve `dist/` git'e girmez — exe commit edilmez, dağıtım klasörüne kopyalanır.

## 2. Hedef makineye kurulum

1. `CorporateCertificate.exe`'yi istediğiniz klasöre kopyalayın.
2. **Aynı klasöre** `corpcert.ini` koyun (şablon: `docs/corpcert.ini.example`). Kullanıcı adı ve parolayı sistem yöneticisinden alın; dosyayı e-posta/sohbetle paylaşmayın.
3. Yanına **hiçbir `.db` dosyası** kopyalanmaz; veri merkezî sunucudadır.

Ortak bir klasörden çalıştırılıyorsa `corpcert.ini`'ye yalnızca yetkili kullanıcıların okuma izni olmalıdır.

## 3. Ortam değişkenleri (isteğe bağlı)

`corpcert.ini` yerine veya üzerine yazmak için. Elle verilir, exe'ye gömülmez.

| Değişken | Açıklama |
|---|---|
| `CORPCERT_SERVER` | SQL Server adresi |
| `CORPCERT_DB` | Veritabanı adı |
| `CORPCERT_USER` | SQL login |
| `CORPCERT_PASSWORD` | Parola |
| `CORPCERT_INIT_SCHEMA` | `1` ise açılışta şema DDL'i çalışır. **Production'da kullanılmaz**; yalnızca yeni/test veritabanı için. |
| `CORPCERT_DOSYA_KLASORU` | Dosya eklerinin ağ klasörü |

## 4. Gereksinimler

- 64-bit Windows; SQL Server'a TCP 1433 erişimi.
- Kullanıcının dosya ağ klasörüne (`\\172.16.0.201\Kurumsal_Video\ProgramFiles\CorporateCertificate\dosyalar`) okuma/yazma izni.

## 5. Veritabanı şeması

Şema `docs/schema.sql`'dedir (idempotent). **Production'a insan tarafından, inceleme sonrası** uygulanır (AGENTS.md §9.4); uygulama varsayılan olarak DDL çalıştırmaz.

```bash
sqlcmd -S <sunucu> -U <yetkili_kullanici> -P <parola> -d CorporateCertificate -i docs/schema.sql
```

Önerilen uygulama login'i (sunucu yöneticisi uygular, AI çalıştırmaz):

```sql
-- master'da
CREATE LOGIN corpcert_app WITH PASSWORD = '<güçlü parola>';
-- CorporateCertificate'te
CREATE USER corpcert_app FOR LOGIN corpcert_app;
GRANT SELECT, INSERT, DELETE ON dbo.activities     TO corpcert_app;
GRANT SELECT, INSERT, DELETE ON dbo.files          TO corpcert_app;
GRANT SELECT, INSERT, DELETE ON dbo.activity_files TO corpcert_app;
```

## 6. Güncelleme

Yeni exe derlenir ve eskisinin üzerine kopyalanır; `corpcert.ini` yerinde kalır. Kullanıcıların uygulamayı kapatmış olması gerekir (açık exe'nin üzerine yazılamaz).
