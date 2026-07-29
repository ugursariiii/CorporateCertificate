/* ===========================================================================
   Kurumsal İletişim Sertifika Programı — MSSQL şeması
   ---------------------------------------------------------------------------
   Hedef veritabanı: CorporateCertificate (SQL Server 2022)
   Bu betik idempotenttir: tekrar tekrar çalıştırılabilir, mevcut veriyi bozmaz.

   Elle çalıştırmak için:
       sqlcmd -S 94.102.74.165 -U sa -P <parola> -d CorporateCertificate -i schema.sql
   Uygulama açılışta aynı DDL'i kendisi de çalıştırır (Database._init_schema).
   =========================================================================== */

IF OBJECT_ID(N'dbo.activities', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.activities (
        id            INT IDENTITY(1,1) NOT NULL,   -- SQLite'taki AUTOINCREMENT karşılığı
        donem         NVARCHAR(9)   NOT NULL,       -- Örn: "2025-2026" (YYYY-YYYY)
        okul          NVARCHAR(50)  NOT NULL,       -- "FENLI" / "KOLEJ"
        seviye        NVARCHAR(10)  NOT NULL,       -- "LH","9","10","11","12"
        etkinlik_adi  NVARCHAR(255) NOT NULL,       -- Örn: "Siemens AI Certificate Program"
        CONSTRAINT PK_activities PRIMARY KEY CLUSTERED (id)
    );
END;
GO

/* Raporlama (retrospective tracking) her aşamada dönem+okul+seviye ile arama
   yapar; sorgunun tamamını karşılayan kapsayıcı (covering) indeks. */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_activities_donem_okul_seviye'
      AND object_id = OBJECT_ID(N'dbo.activities')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_activities_donem_okul_seviye
        ON dbo.activities (donem, okul, seviye)
        INCLUDE (etkinlik_adi);
END;
GO

/* Kayda eklenen dosyalar. Dosyanın kendisi veritabanında değil, paylaşılan ağ
   klasöründe durur:
       \\172.16.0.201\Kurumsal_Video\ProgramFiles\CorporateCertificate\dosyalar
   Burada yalnızca üstveri tutulur; saklanan_ad o klasördeki gerçek dosya adıdır. */
IF OBJECT_ID(N'dbo.files', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.files (
        id              INT IDENTITY(1,1) NOT NULL,
        dosya_adi       NVARCHAR(255)  NOT NULL,   -- Kullanıcının gördüğü özgün ad
        saklanan_ad     NVARCHAR(260)  NOT NULL,   -- Klasördeki ad: "rapor_9f3c1ab2.pdf"
        boyut           INT            NOT NULL,   -- Bayt cinsinden
        yuklenme_tarihi DATETIME2(0)   NOT NULL
            CONSTRAINT DF_files_yuklenme_tarihi DEFAULT SYSDATETIME(),
        CONSTRAINT PK_files PRIMARY KEY CLUSTERED (id)
    );
END;
GO

/* Dosyalar bir dönem VARBINARY olarak veritabanında saklanmıştı; eski şemaya
   sahip bir veritabanına karşı çalışıldığında kolon burada eklenir. */
IF COL_LENGTH('dbo.files', 'saklanan_ad') IS NULL
    ALTER TABLE dbo.files ADD saklanan_ad NVARCHAR(260) NULL;
GO

/* Kayıt <-> dosya bağı (çoka-çok). Giriş formu seçilen her okul x seviye
   kombinasyonu için ayrı bir activities satırı ürettiğinden, aynı dosya bir kez
   saklanıp oluşan tüm kayıtlara bağlanır (içerik kopyalanmaz). */
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
END;
GO

/* Sahipsiz kalan dosyaları bulmak (file_id üzerinden arama) için; birincil
   anahtar activity_id ile başladığından bu yön indekssiz kalırdı. */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'IX_activity_files_file'
      AND object_id = OBJECT_ID(N'dbo.activity_files')
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_activity_files_file
        ON dbo.activity_files (file_id);
END;
GO
