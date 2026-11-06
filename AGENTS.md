# AGENTS.md

> Tüm projelerde ortak kullanılan AI geliştirme talimatlarıdır (Claude Code, Codex, Cursor, Copilot).
> Yalnızca **§0 Proje Bilgileri** projeye göre doldurulur; geri kalan bölümler tüm projelerde aynı kalır.
> Projeye özgü sapmalar ve notlar `docs/MIMARI.md`'ye yazılır (§4 "Kök dizin ve docs/ düzeni").

---

## 0. Proje Bilgileri

| Alan | Değer |
|---|---|
| Proje adı (`<App>`) | `CorporateCertificate` (Kurumsal İletişim Sertifika Programı) |
| Amaç | Kurumsal sertifika programlarını (Siemens, Cervantes, Özyeğin vb.) dönem/okul/seviye bazında kaydetmek ve öğrencinin geçmiş yıllarına geriye doğru raporlamak. |
| Hedef kullanıcı | Kurumsal İletişim birimi personeli (kurum içi Windows masaüstü) |
| Target framework | **Python 3.14 + PyQt6** masaüstü uygulaması (.NET değil — sapmalar `docs/MIMARI.md`) |
| Database | SQL Server 2022 (merkezî, `pymssql` ile) — **tek ortam: production** |
| Authentication | Yok (uygulama içi kullanıcı girişi yok; DB'ye ortak SQL login ile bağlanır) |
| Dış API'ler (tüketilen) | Yok — dosya ekleri paylaşılan ağ klasörüne (`\\172.16.0.201\...`) yazılır |
| Dışa açık API (sunulan) | Yok |
| UI dili | Varsayılan `tr` |
| Render mode | Yok (PyQt6 masaüstü) |
| MAUI Hybrid | Planlanmadı |

Projeye özgü notlar ve bu dosyadan sapmalar: [docs/MIMARI.md](docs/MIMARI.md)

---

## 1. Kural Önceliği

Çelişki durumunda bu sıra uygulanır:

1. **Production veritabanı ve canlı dış servis güvenliği** (§9, §11.5)
2. **Güvenlik ve secret'lar** (§10)
3. Kullanıcının mevcut görev için verdiği açık talimat
4. Bu dosya
5. Mevcut projenin convention'ları
6. Framework best practice'leri
7. AI'ın kendi tercihi

"Gerekeni yap", "sorunu çöz", "projeyi bitir" gibi genel ifadeler **production veritabanında işlem yetkisi vermez.**

---

## 2. Çalışma Şekli

**AI'ın inisiyatif kullanması beklenir.** Daha iyi mimari, daha güvenli veya daha performanslı bir yol görürsen öner ve gerekçesini söyle. Kullanıcının önerisi hatalı, güvensiz veya güncelliğini yitirmişse açıkça belirt:
`"Bu uygulanabilir; ancak X nedeniyle Y daha doğru olur."`

Her görevde:

1. **Keşfet:** İlgili kodu, kullanım noktalarını ve mevcut convention'ları incele. Proje kökünü ve `docs/` düzenini §4'teki "Kök dizin ve docs/ düzeni" kuralına göre denetle.
2. **Planla:** Etki alanını değerlendir. Geniş kapsamlı değişiklikte önce kısa bir plan sun.
3. **Uygula:** Problemi çözen en sade çözümü uygula. Küçük bir iş için büyük bir yapı kurma.
4. **Doğrula:** Build ve testleri çalıştır (§15).
5. **Raporla:** §16'daki formatı kullan.

Kurallar:

- **Root cause:** Hatanın gerçek nedenini bul. Semptomu gizleyen workaround (her yere `?.` / `!` / `try-catch` eklemek gibi) üretme. Sırayla bak: hata mesajı → stack trace → data flow → config/DI → DB mapping → auth → environment.
- Çalışan davranışı gereksiz yere bozma. Değişmeyen dosyaları yeniden yazma.
- Compile/test edilmemiş kodu "tamamlandı" diye raporlama.
- Belirsiz ve geri dönüşü zor bir kararda varsayım yapma, sor.
- **Fazlı çalışma:** Kullanıcı "her faz sonrası onayımı bekle" dediyse açık onay almadan sonraki faza geçme.

---

## 3. Mimari

**Feature-based (vertical slice)** yapı kullanılır. Bir özelliğe ait endpoint, service, DTO ve sayfalar katman tipine göre dağıtılmaz; aynı feature klasöründe durur.

```text
UI (Razor component)  ──►  I[Feature]Service  ◄──  Minimal API endpoint
                                   │
                          [Feature]Service (business logic)
                                   │
                              AppDbContext  ──►  Database
```

- **UI ve API aynı service'i kullanır.** Business logic tek yerde bulunur.
- UI yalnızca `<App>.Shared` içindeki interface'e bağımlıdır. Böylece MAUI veya WASM host'unda aynı UI, `HttpClient` tabanlı bir implementasyonla çalışır.
- **Service doğrudan `AppDbContext` kullanır.** EF Core zaten Unit of Work ve Repository sağlar. Generic repository oluşturma. Repository yalnızca karmaşık ve tekrar eden sorgu mantığı varsa, gerekçesi açıklanarak eklenir.
- Endpoint ince olur: input alır, service'i çağırır, `TypedResults` döndürür. Endpoint'te business logic veya `DbContext` bulunmaz.
- Component; UI state, loading/empty/error durumları ve validation mesajlarından sorumludur. Kritik business kuralı yalnızca UI'da bulunmaz.
- **Mevcut projeler:** Farklı ama tutarlı bir yapı varsa, istenmeden toplu yeniden yapılandırma yapma. Yeni feature'ları bu standarda göre ekle ve geçiş önerisini ayrıca sun.

---

## 4. Solution ve Klasör Yapısı

```text
<App>/
├── <App>.slnx
├── global.json                    # SDK sürümü sabitlenir
├── Directory.Build.props          # Ortak build ayarları
├── Directory.Packages.props       # Central Package Management
├── .editorconfig                  # Kod stili (build'de zorunlu)
├── .gitattributes                 # Satır sonları (CRLF) ve ikili dosyalar
├── .gitignore
├── .gitlab-ci.yml                 # Yalnızca CI/CD kullanan projede (GitLab kökte arar)
├── AGENTS.md
├── CLAUDE.md
├── docs/                          # Proje belgeleri ve yayın/kurulum dosyaları (aşağıda "Kök dizin ve docs/ düzeni")
│   ├── MIMARI.md                  # Projeye özgü notlar ve AGENTS.md'den sapmalar
│   └── iis-yayini.md              # IIS yayını, sunucu ortam değişkenleri
├── src/
│   ├── <App>.Web/                 # Host: Blazor Web App + Minimal API + EF Core
│   │   ├── Program.cs
│   │   ├── Components/App.razor   # Yalnızca HTML host
│   │   ├── Data/
│   │   │   ├── AppDbContext.cs
│   │   │   ├── Entities/[Entity].cs
│   │   │   ├── Configurations/[Entity]Configuration.cs
│   │   │   └── Migrations/
│   │   ├── Features/
│   │   │   └── [Feature]s/
│   │   │       ├── [Feature]Endpoints.cs
│   │   │       ├── [Feature]Service.cs
│   │   │       ├── [Feature]Hub.cs              # Yalnızca gerekiyorsa
│   │   │       └── [Feature]FeatureExtensions.cs # Add[Feature]Feature() / Map[Feature]Endpoints()
│   │   ├── Infrastructure/        # Cross-cutting: ErrorHandling, Auth, Options, Extensions
│   │   ├── Integrations/          # Dış API client'ları (§11)
│   │   └── Properties/launchSettings.json
│   ├── <App>.UI/                  # Razor Class Library — MAUI'de yeniden kullanılır
│   │   ├── Routes.razor
│   │   ├── Layout/
│   │   ├── Components/            # Feature'dan bağımsız ortak component'ler
│   │   ├── Features/
│   │   │   └── [Feature]s/
│   │   │       ├── [Feature]List.razor
│   │   │       ├── [Feature]Create.razor
│   │   │       ├── [Feature]Edit.razor
│   │   │       └── [Feature]Form.razor   # Create/Edit ortak formu
│   │   ├── Resources/             # .resx (çok dilliyse)
│   │   └── wwwroot/
│   └── <App>.Shared/              # Contract'lar: hem Web hem UI referans verir
│       ├── Common/                # PagedQuery, PagedResult<T>, Result<T>
│       └── Features/
│           └── [Feature]s/
│               ├── I[Feature]Service.cs
│               ├── [Feature]Dtos.cs       # Request/Response record'ları
│               └── [Feature]Enums.cs      # Yalnızca gerekiyorsa
└── tests/
    ├── <App>.Web.Tests/           # Unit + integration (WebApplicationFactory)
    └── <App>.UI.Tests/            # bUnit component testleri
```

Kurallar:

- Bağımlılık yönü: `Web → UI → Shared` ve `Web → Shared`. **Shared hiçbir projeye referans vermez; UI, Web'e referans vermez.**
- WASM veya MAUI eklendiğinde: `src/<App>.Client/` (servislerin `HttpClient` implementasyonları) ve `src/<App>.Maui/` (host) projeleri eklenir. Mevcut yapı değişmez.
- RCL'deki sayfalar için `MapRazorComponents<App>().AddAdditionalAssemblies(typeof(<App>.UI._Imports).Assembly)` gerekir.
- Feature klasörü çoğul (`Categories`), entity tekil (`Category`) olur.
- `Helpers`, `Utils`, `Common`/`Manager` gibi amacı belirsiz sınıf veya klasör oluşturma. Kod ya bir feature'a ya da `Infrastructure/` altında amacı belli bir alt klasöre aittir.

### Kök dizin ve docs/ düzeni (tüm projelerde aynı)

Tüm projeler aynı kök ve dokümantasyon düzenini kullanır. **AI her görevin Keşfet adımında projenin kökünü bu kurala göre denetler.** Uymayan bir şey görürse, kullanıcının ayrıca söylemesini beklemeden düzeltir. Düzeltme geniş kapsamlıysa önce önerir. Taşıma veya silme öncesi hedefin içeriğine bakılır, §14 geçerlidir.

- **Kökte yalnızca şunlar bulunur:** `.editorconfig`, `.gitattributes`, `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `Directory.Build.props`, `Directory.Packages.props`, `global.json`, `<App>.slnx`, `docs/`, `src/`, `tests/`. CI/CD kullanan projede ayrıca `.gitlab-ci.yml` bulunur.
- **Başka kök klasör açılmaz:** `deploy/`, `ci/`, `scripts/`, `tools/`, `build/`, `.config/` gibi klasörler oluşturulmaz. Yayın ve kurulum script'leri ile yardımcı dosyalar (`deploy.ps1`, `Setup-LocalIis.ps1`, `app_offline.htm` vb.) `docs/` altında durur. Derleme çıktısı (`artifacts/`, `publish/`) yalnızca `.gitignore`'da yer alır.
- **Kökte başka `.md` dosyası bulunmaz:** `README.md`, `DEPLOYMENT.md` gibi dosyalar açılmaz. Kurumsal ortak kılavuzlar (`gitlab.md` vb.) projeye kopyalanmaz; kaynakları `MarkdownSourceFile` klasörüdür.
- **Yerel araç manifest'i eklenmez:** `dotnet-tools.json` kullanılmaz. CI'da gereken araç (örn. `dotnet-ef`) job içinde sürümü sabitlenerek kurulur.
- **`docs/` içeriği:**
  - `MIMARI.md`: projeye özgü notlar. Proje özeti, **AGENTS.md'den sapmalar** tablosu (`AGENTS.md | Bu projede | Gerekçe`), komutlar, mimari, klasör düzeni ve yapılandırma burada yer alır. Sapmalar AGENTS.md'ye değil, buraya yazılır.
  - `iis-yayini.md`: yayın belgesidir. Publish, güncelleme adımları (CI varsa CI'ın yaptıkları), sunucuda elle verilen ortam değişkenleri tablosu ve projeye göre veritabanı şeması / ek kurulum adımlarını içerir.
  - `GECIS_ONERISI.md` (gerekirse): AGENTS.md'ye tam uyum için geçiş önerisidir (§3).
  - Projeye özgü diğer belgeler: sayfa listesi, checklist, şablonlar vb.
- **`AGENTS.md`:** Bu dosyanın birebir kopyasıdır. Projede yalnızca §0 doldurulur ve tablonun altına `docs/MIMARI.md` bağlantısı konur. Ortak kural değişikliği önce `MarkdownSourceFile/AGENTS.md`'de yapılır, sonra projelere kopyalanır.
- **`CLAUDE.md`:** Proje bilgisi (mimari, komutlar) buraya yazılmaz, `docs/MIMARI.md`'ye yazılır. Biçimi şöyledir:

  ```markdown
  @AGENTS.md
  @docs/MIMARI.md

  <!-- Ortak kurallar AGENTS.md dosyasındadır. Buraya yalnızca Claude Code'a özgü notlar eklenir. -->

  ## Claude Code notları

  - ...
  ```

- **`.gitattributes`:** `* text=auto eol=crlf` satırını içerir; ikili dosyalar (`*.png`, `*.ico`, `*.xlsx` …) `binary` olarak işaretlenir.

### Ortak build ayarları

```xml
<!-- Directory.Build.props -->
<Project>
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <AnalysisLevel>latest-recommended</AnalysisLevel>
    <EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>
  </PropertyGroup>
</Project>
```

Paket sürümleri yalnızca `Directory.Packages.props` dosyasında tutulur. `.csproj` dosyalarında `Version` yazılmaz.

---

## 5. Kod Standartları

İsimlendirme ve format `.editorconfig` ile zorunlu tutulur. Ek kurallar:

- Teknik isimler (class, method, klasör, dosya, tablo, kolon) **İngilizce** olur. UI metinleri proje dilinde yazılır.
- Her dosyada tek bir public tip bulunur, dosya adı tip adıyla aynı olur. İstisna: aynı feature'ın DTO record'ları tek bir `[Feature]Dtos.cs` dosyasında toplanabilir.
- File-scoped namespace kullan. DI için primary constructor kullan. DTO'lar `record` olur. Türetilmeyecek sınıflar `sealed` olur.
- **Nullable:** Gerçekten nullable olanı `?` ile modelle. Uyarıyı `!` veya `null!` ile bastırma; zorunluysa gerekçesini comment olarak yaz.
- **Async:** Tüm I/O işlemleri async olur, method'lar `Async` son ekini alır. `CancellationToken` endpoint'ten DB'ye kadar taşınır. `.Result` ve `.Wait()` kullanılmaz.
- **DI:** Business bağımlılıkları `new` ile oluşturulmaz. Feature kayıtları `Add[Feature]Feature()` extension'ında toplanır.
- **Configuration:** Options pattern kullan (`AddOptions<T>().BindConfiguration(...).ValidateDataAnnotations().ValidateOnStart()`).
- **Tarih/saat:** Kalıcı zamanlar UTC tutulur (`DateTimeOffset` veya UTC `DateTime`). `DateTime.Now` yerine inject edilen `TimeProvider` kullanılır. Kullanıcıya gösterirken dönüştürülür.
- **Comment:** "Ne yaptığını" değil, "neden yaptığını" açıklar (business kuralı, teknik kısıt, güvenlik gerekçesi, dış sistem davranışı).
- KISS / YAGNI / SRP dengeli uygulanır. Okunabilir kod, "akıllı" ama karmaşık koddan değerlidir.

---

## 6. Veri Erişimi (EF Core)

- Primary key varsayılan olarak `int Id` olur. Tablo ve kolon isimleri İngilizcedir.
- Entity mapping `IEntityTypeConfiguration<T>` ile `Data/Configurations/` altında yapılır.
- **Entity, API veya UI contract'ı olarak kullanılmaz.** Dışarıya her zaman DTO döner. Mapping elle yazılır (projection veya extension method). AutoMapper/MediatR gibi paketler varsayılan olarak eklenmez.
- Read sorgularında `.Select()` projection ile yalnızca gereken alanları çek. Tracking gerekmiyorsa `AsNoTracking()` kullan.
- Filtering, sorting ve pagination **database seviyesinde** yapılır. Tabloyu belleğe çekip filtreleme yapılmaz.
- N+1 sorgu ve gereksiz `Include()` kullanılmaz. Gereksiz `SaveChangesAsync()` çağrılmaz.
- Raw SQL gerekiyorsa yalnızca parametreli olur (`FromSql($"...")`). String concatenation kullanılmaz.

```csharp
var items = await db.Categories
    .AsNoTracking()
    .Where(x => x.IsActive)
    .OrderBy(x => x.Name)
    .Skip((query.Page - 1) * query.PageSize).Take(query.PageSize)
    .Select(x => new CategoryListItem(x.Id, x.Name))
    .ToListAsync(ct);
```

---

## 7. API Standardı (Minimal API)

```csharp
public static class CategoryEndpoints
{
    public static IEndpointRouteBuilder MapCategoryEndpoints(this IEndpointRouteBuilder app)
    {
        var group = app.MapGroup("/api/categories").WithTags("Categories").RequireAuthorization();

        group.MapGet("/", GetListAsync);
        group.MapGet("/{id:int}", GetByIdAsync);
        group.MapPost("/", CreateAsync);
        group.MapPut("/{id:int}", UpdateAsync);
        group.MapDelete("/{id:int}", DeleteAsync);
        return app;
    }

    private static async Task<Results<Ok<CategoryResponse>, NotFound>> GetByIdAsync(
        int id, ICategoryService service, CancellationToken ct)
        => await service.GetByIdAsync(id, ct) is { } item ? TypedResults.Ok(item) : TypedResults.NotFound();
}
```

- Route'lar resource-oriented ve çoğul olur (`/api/categories/{id}`).
- Status code: `200`, `201` (+Location), `202`, `204`, `400`, `401`, `403`, `404`, `409`, `412`, `429`. Hata gövdesi **ProblemDetails (RFC 9457)** formatında olur.
- OpenAPI için built-in `AddOpenApi()` / `MapOpenApi()` kullanılır. Dışa açık API yoksa yalnızca Development'ta açılır. Dışa açık API varsa doküman contract'tır ve yayınlanır (§7.1).
- Request modeli yalnızca istemcinin değiştirebileceği alanları içerir. Create ve Update ihtiyaçları farklıysa tek modele zorlama.
- Response'ta stack trace, SQL, connection string, sunucu yolu veya iç exception detayı bulunmaz.

### 7.1 Dışa Açık API (partner / mobil / public istemciler)

API, kendi Blazor UI'ımız dışındaki istemcilere açıldığında bu bölüm uygulanır. Mağazada yayınlanan kendi MAUI uygulamamız da bu kapsamdadır, çünkü eski sürümler sahada çalışmaya devam eder.

**Bu durumda API bir contract'tır. Mevcut istemcileri bozan değişiklik yapılamaz.**

#### Versiyonlama ve contract

- `Asp.Versioning.Http` kullanılır ve versiyon URL'de taşınır: `/api/v1/categories`.
- **Breaking change** (yeni versiyon gerektirir): alan silme veya yeniden adlandırma, tip değişikliği, yeni zorunlu request alanı, status code veya davranış değişikliği.
- **Non-breaking** (aynı versiyonda yapılabilir): opsiyonel alan ekleme, yeni endpoint ekleme.
- Eski versiyon hemen kaldırılmaz. Önce `Deprecation` / `Sunset` header'ları ile duyurulur, kaldırma tarihini kullanıcı belirler.
- Versiyona özel DTO'lar `V1/`, `V2/` alt klasörlerinde tutulur. Entity veya iç DTO, versiyonsuz olarak dışarı açılmaz.
- Serileştirme kuralları: enum'lar **string** olarak (`JsonStringEnumConverter`), tarihler ISO 8601 UTC olarak serileştirilir. Liste yanıtları `PagedResult<T>` envelope'u ile döner.
- OpenAPI dokümanı build sırasında üretilir. CI'da önceki sürümle diff alınarak breaking change yakalanır.

```csharp
var categories = app.NewVersionedApi("Categories")
    .MapGroup("/api/v{version:apiVersion}/categories")
    .HasApiVersion(1)
    .RequireAuthorization("categories:read")
    .RequireRateLimiting("per-client");
```

#### Kimlik doğrulama ve yetki

- **Makineden makineye (partner backend):** OAuth 2.0 client credentials (JWT bearer) tercih edilir. Basit senaryoda API key kullanılabilir. API key şu kurallara uyar:
  - `X-Api-Key` header'ında taşınır, query string'de taşınmaz.
  - Her client için ayrı üretilir.
  - DB'de hash'lenmiş olarak saklanır.
  - İptal edilebilir ve yenilenebilir.
- **Kullanıcı adına (mobil/SPA):** OIDC authorization code + PKCE kullanılır. Access token kısa ömürlüdür, süresi refresh token ile uzatılır.
- Yetki scope/policy ile verilir (`categories:read`, `categories:write`). Her client yalnızca izinli endpoint'lere erişir.
- **Client/tenant izolasyonu:** Bir client yalnızca kendi verisine erişir. Bu kontrol sorgu seviyesinde yapılır (global query filter veya service filtresi).
- AI, production ortamında API key veya client secret **üretmez, yenilemez veya iptal etmez**. Gerekli adımları yalnızca dokümante eder.

#### Koruma ve limitler

- Rate limiting client bazında uygulanır (`AddRateLimiter`, partition: client id). Limit aşıldığında `429` ve `Retry-After` header'ı döner.
- CORS yalnızca API tarayıcıdan çağrılıyorsa açılır. Bu durumda açık bir origin whitelist kullanılır. `AllowAnyOrigin` credentials ile birlikte kullanılmaz. Server-to-server çağrılarda CORS gerekmez.
- Request body boyutu sınırlandırılır. Sayfa boyutu en fazla `100` olur.

#### Güvenilirlik

- **Idempotency:** Kritik create işlemleri (sipariş, ödeme) `Idempotency-Key` header'ını destekler. Aynı key ile gelen tekrar isteğe ilk yanıt döner, işlem ikinci kez yapılmaz.
- **Concurrency:** Update işlemlerinde `ETag`/`If-Match` veya `rowversion` kullanılır. Çakışmada `412`/`409` döner, kayıt sessizce ezilmez.
- **Uzun işlemler:** `202 Accepted` ve bir durum sorgulama endpoint'i kullanılır.
- **Giden webhook** (istemcilere event gönderiliyorsa):
  - Gövde HMAC ile imzalanır.
  - Her event benzersiz bir `eventId` taşır.
  - Başarısız gönderim backoff ile tekrar denenir.

#### Gözlemlenebilirlik

- Log ve metriklerde client id bulunur. Yanıtta trace id döner, böylece istemci hatayı bildirirken referans verebilir.

---

## 8. Validation ve Error Handling

- Input validation `DataAnnotations` ile yapılır. Minimal API tarafında built-in validation açık olur (`AddValidation()`). Aynı DTO, UI'da `DataAnnotationsValidator` ile kullanılır.
- Business ve cross-field kuralları service katmanında kontrol edilir. **UI validation, backend validation'ın yerine geçmez.**
- Validation mesajı ilgili input'un hemen altında gösterilir (`<ValidationMessage For="..." />`).
- **Beklenen business hataları** (bulunamadı, çakışma, kural ihlali) service'ten `Result<T>` olarak döner ve endpoint'te uygun status code'a çevrilir.
- **Beklenmeyen hatalar** exception olarak kalır ve merkezi olarak yakalanır: `AddProblemDetails()` + `IExceptionHandler` + `UseExceptionHandler()`.
- Her method'a `try/catch` eklenmez. Boş `catch` kullanılmaz. Exception sessizce yutulmaz. Kullanıcıya ham exception mesajı gösterilmez, teknik detay log'a yazılır.

---

## 9. ⚠️ Veritabanı Güvenliği — MUTLAK KURAL

### 9.1 Production veritabanı dokunulmazdır

AI production / yayın veritabanında **hiçbir yazma işlemi yapamaz**. Bunun hiçbir istisnası yoktur: varsayım, kolaylık, optimizasyon, "backup vardır" düşüncesi veya kullanıcının genel bir talimatı istisna oluşturmaz.

Yasak işlemler:

- **Veri:** `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `MERGE`, seed/test verisi, veri düzeltme, toplu güncelleme.
- **Şema:** `CREATE`, `ALTER`, `DROP`, `RENAME`, kolon/tip/nullable/PK/FK/index/constraint değişikliği, `dotnet ef database update`.
- **Dosya** (`.db`, `.sqlite`, `.mdf` vb. ve backup'ları): silme, taşıma, yeniden adlandırma, üzerine yazma, reset, yeniden oluşturma.
- **Startup/deploy:** Production'da otomatik `Database.Migrate()`, `EnsureCreated()`, `EnsureDeleted()`, seed veya reset. Bunlar yalnızca `app.Environment.IsDevelopment()` kontrolü arkasında olabilir. Deploy script'ine migration veya seed eklenmez.
- **Publish:** Local DB dosyası publish çıktısına girmez ve production dosyasının üzerine kopyalanmaz (`CopyToPublishDirectory="Never"`). Dosya tabanlı DB'nin yolu publish klasörünün dışında olur.

**Production şeması yetkili şemadır.** Uygulama modeli production'a uydurulur, production uygulama modeline uydurulmaz.

### 9.2 Ortam doğrulama

DB'yi değiştirecek her işlemden önce şunları kontrol et: connection string'in host/database adı, `ASPNETCORE_ENVIRONMENT`, aktif `appsettings.*.json`, DB dosyasının fiziksel yolu, uygulamanın publish klasöründe çalışıp çalışmadığı.

```text
ORTAM KESİN OLARAK LOCAL DOĞRULANAMIYORSA → PRODUCTION KABUL ET → İŞLEM YAPMA
```

`CRITICAL — PRODUCTION` başlığıyla verilen bir bağlantı bilgisi hiçbir koşulda local kabul edilmez.

### 9.3 Production read-only erişim

Yalnızca kullanıcı açıkça izin verirse ve teşhis, doğrulama veya şema inceleme amacıyla yapılır. Varsa read-only kullanıcı veya read replica tercih edilir. Sorgular filtreli ve sınırlı olur (`TOP`/`LIMIT`, `SELECT *` kullanılmaz). Uzun transaction açılmaz, lock oluşturulmaz. Hassas kişisel veri gereksiz yere görüntülenmez.

### 9.4 Production'da sorun tespit edilirse

Sorun düzeltilmez, raporlanır. İstenirse SQL veya `dotnet ef migrations script --idempotent` çıktısı **hazırlanır ama çalıştırılmaz**. Script'i insan inceleyip uygular.

```text
TESPİT: ...
ETKİSİ: ...
ÖNERİLEN ÇÖZÜM: ...
PRODUCTION DATABASE'E UYGULANMADI.
```

### 9.5 Local / development veritabanı

- `migrations add` yalnızca kod üretir ve serbesttir. `database update`, şema değişikliği ve test verisi işlemleri **yapılmadan önce kullanıcıya bildirilir**:
  `"LOCAL DB'de: Orders tablosuna Status kolonu eklenecek, migration yalnızca local'e uygulanacak. Production etkilenmeyecek."`
- **Destructive işlemler** (DB silme/reset, drop table/column, toplu silme, geri dönüşsüz veri dönüşümü) için veri kaybı riski belirtilir ve **kullanıcı onayı beklenir.**

---

## 10. Güvenlik ve Secret'lar

### Secret'lar

Secret şunları kapsar: password, API key, token, private key, client secret, auth cookie, connection string (production connection string **kritik credential**'dır) ve test hesabı bilgileri.

Secret'lar:

- Source code'a, `appsettings*.json` dosyasına, teste, dokümantasyona veya örnek config'e **gerçek değeriyle** yazılmaz. Git'e commit edilmez.
- Log'a, console'a veya chat çıktısına yazdırılmaz.
- Development ortamında **User Secrets** veya environment variable üzerinden sağlanır. Production ortamında environment variable veya secret store (Key Vault vb.) üzerinden sağlanır.
- `appsettings.json` içinde yalnızca boş anahtar bulunur (`"ApiKey": ""`).

### Uygulama güvenliği

- Tüm kullanıcı girdisi güvenilmez kabul edilir ve server-side doğrulanır.
- **Secure by default:** Fallback authorization policy authenticated kullanıcı ister. Public endpoint'ler açıkça `AllowAnonymous()` ile işaretlenir.
- Yetki kontrolü backend'de yapılır. UI'da buton gizlemek authorization sayılmaz. Kullanıcının gönderdiği ID ile kayda erişirken sahiplik kontrolü yapılır (resource-based authorization, IDOR'a karşı).
- Sorting ve filter alan adları whitelist ile sınırlanır. Kullanıcıdan gelen string, kolon adı olarak kullanılmaz.
- XSS, CSRF (antiforgery) ve injection riskleri gözetilir. HTTPS/HSTS açık olur. Public endpoint'lerde rate limiting uygulanır.
- Password için framework mekanizması (Identity) kullanılır, kendi hashing algoritmanı yazma. Token süreleri kısa tutulur.
- Hassas veri client-side storage'da tutulmaz.

### Logging

- `ILogger<T>` ve structured logging kullanılır (`logger.LogInformation("Order {OrderId} created", id)`). Uygulama log'u için `Console.WriteLine` kullanılmaz.
- Secret ve hassas kişisel veri loglanmaz.

---

## 11. Dış API Entegrasyonu

İki senaryo vardır:

- **A. Ek kaynak:** Uygulamanın kendi DB'si vardır, ayrıca dış servisler (ödeme, SMS, ERP, kur vb.) çağrılır.
- **B. Ana kaynak:** Uygulamanın kendi DB'si yoktur veya sınırlıdır, veriler dış API'den gelir.

### 11.1 Yapı

```text
src/<App>.Web/Integrations/
└── [Provider]/                                   # Örn. Erp, Iyzico, Netgsm
    ├── [Provider]Client.cs                       # Typed HttpClient
    ├── [Provider]Options.cs                      # BaseUrl, ApiKey (appsettings'te boş)
    ├── [Provider]Models.cs                       # Dış API'nin kendi modelleri (internal)
    └── [Provider]ServiceCollectionExtensions.cs  # Add[Provider]Integration()
```

- Akış: `UI → I[Feature]Service → [Feature]Service → [Provider]Client → Dış API`. Senaryo B'de `[Feature]Service`, `DbContext` yerine client'ı kullanır. UI, Shared ve endpoint yapısı değişmez.
- **Dış modeller dışarı sızmaz (anti-corruption layer).** `[Provider]Models` `internal` tanımlanır. Bu modeller Shared'a, UI'a veya API response'una çıkmaz, client içinde kendi DTO'larımıza map edilir. Dış API değiştiğinde yalnızca bu klasör değişir.
- **Secret gerektiren dış API, MAUI veya WASM client'ından doğrudan çağrılmaz**, çünkü secret cihaza veya tarayıcıya iner. Bu çağrılar her zaman kendi backend'imiz üzerinden yapılır (BFF). Secret gerektirmeyen public API'ler `<App>.Client` içinden çağrılabilir.
- Provider'ın sandbox ortamı yoksa, Development'ta interface arkasında fake bir implementasyon register edilir.

### 11.2 HttpClient

- `IHttpClientFactory` ve typed client kullanılır. `new HttpClient()` kullanılmaz.
- BaseUrl Options'tan, API key secret store'dan gelir (§10). `CancellationToken` client'a kadar taşınır.
- Resilience için `AddStandardResilienceHandler()` kullanılır (timeout, retry, circuit breaker).
- **Idempotent olmayan çağrılar (POST, ödeme) körlemesine tekrarlanmaz.** Bunun için `DisableForUnsafeHttpMethods()` kullanılır veya provider destekliyorsa idempotency key gönderilir.

```csharp
builder.Services.AddOptions<ErpOptions>()
    .BindConfiguration("Integrations:Erp").ValidateDataAnnotations().ValidateOnStart();

builder.Services.AddHttpClient<ErpClient>((sp, http) =>
{
    var options = sp.GetRequiredService<IOptions<ErpOptions>>().Value;
    http.BaseAddress = new Uri(options.BaseUrl);
    http.DefaultRequestHeaders.Add("X-Api-Key", options.ApiKey);
})
.AddStandardResilienceHandler();
```

### 11.3 Yanıt ve hata yönetimi

- Dış yanıt güvenilmez veri olarak ele alınır. Status code kontrol edilir, eksik veya null alanlara karşı koruma yapılır. Beklenmeyen format, kontrolsüz bir exception yerine kontrollü bir hataya çevrilir.
- Dış hata `Result<T>` olarak döner. Kullanıcıya genel bir mesaj ve `502`/`503` ProblemDetails gösterilir. Dış servisin ham hata gövdesi kullanıcıya gösterilmez.
- Log'a endpoint, status code, süre ve correlation id yazılır. Request/response body içindeki secret ve kişisel veri loglanmaz.

### 11.4 Performans ve limitler

- Sık değişmeyen okumalar `HybridCache` ile cache'lenir. Cache süresi bilinçli seçilir.
- Provider'ın rate limit'ine uyulur. Döngü içinde tek tek çağrı yapılmaz (N+1 HTTP); toplu endpoint varsa o kullanılır.
- Dış API'nin pagination'ı `PagedResult<T>` yapısına çevrilir. Dış API sorting/filter desteklemiyorsa bu durum kullanıcıya bildirilir. Büyük veri belleğe çekilip filtrelenmez.

### 11.5 ⚠️ Canlı dış servis güvenliği

Production DB kuralı (§9) canlı dış servisler için de aynen geçerlidir:

- AI, canlı dış API'ye **yazma veya yan etki oluşturan çağrı yapmaz**: ödeme, iade, SMS/e-posta gönderimi, sipariş, kayıt oluşturma/silme.
- Geliştirme ve testlerde provider'ın **sandbox/test ortamı** kullanılır. Ortam belirsizse **canlı kabul edilir.**
- Canlı ortamda okuma çağrısı yalnızca kullanıcı izniyle ve sınırlı olarak yapılır.
- Gelen webhook'larda imza doğrulanır. Webhook'lar idempotent işlenir, çünkü aynı event birden fazla kez gelebilir.

### 11.6 Test

- Testler gerçek dış API'yi çağırmaz. Bunun yerine `HttpMessageHandler` fake'i veya WireMock.Net kullanılır.
- Test edilecek durumlar: başarılı yanıt, `4xx`, `5xx`, timeout, bozuk veya eksik yanıt.

---

## 12. UI Standartları (Blazor)

### Sayfalar

- CRUD işlemleri ayrı sayfalarda yapılır: `[Feature]List`, `[Feature]Create`, `[Feature]Edit`. Ortak form `[Feature]Form` component'inde tutulur. Route'lar: `/categories`, `/categories/create`, `/categories/{id:int}/edit`.
- Delete işlemi için kullanıcı onayı alınır. Onay, uygulama içi bir dialog component'i ile yapılır (JS `confirm()` kullanılmaz).
- Her veri ekranında **loading**, **empty** ve **error** durumları bulunur.

### Listeleme

- Pagination, sorting, filtering ve search **server-side** yapılır. `PagedQuery` → `PagedResult<T>` kullanılır. Varsayılan sayfa boyutu `20`, maksimum `100` olur.
- Sıralanabilir kolon başlığına her tıklamada yön değişir (asc ↔ desc). Aktif kolon ve yön görsel olarak gösterilir.

### SignalR (yalnızca gerçek zamanlı ihtiyaç varsa)

Hub feature klasöründe durur. Event'ler `[Entity]Created/Updated/Deleted` şeklinde adlandırılır. Reconnect durumu ele alınır, `Dispose` sırasında subscription temizlenir, duplicate subscription oluşturulmaz. Tüm liste yeniden yüklenmez, yalnızca değişen kayıt güncellenir.

### Responsive ve MAUI uyumu

- Mobile, tablet ve desktop desteklenir. Formlar mobilde tek kolon olur. Yatay scroll yalnızca data table'larda kullanılır.
- UI yalnızca `<App>.Shared` interface'lerine bağımlıdır. Browser'a özel API ve JS interop gerekçesiz kullanılmaz. Platforma özel ihtiyaçlar interface arkasına alınır.

### Erişilebilirlik

Her input'un `<label>`'ı bulunur (placeholder label yerine kullanılmaz). Tıklanabilir öğeler `<button>` veya `<a>` olur, `div` olmaz. Icon-only butonlarda `aria-label` bulunur. Anlam yalnızca renkle verilmez. Klavye navigasyonu çalışır. Validation mesajları input'a bağlanır.

### SEO

Yalnızca public sayfalarda uygulanır: semantic HTML, sayfaya özgü `<PageTitle>`, meta description, heading hiyerarşisi, canonical URL ve Open Graph. Admin ve login ekranlarında SEO çalışması yapılmaz.

### Localization

Çok dilli projelerde UI metinleri `Resources/*.resx` ve `IStringLocalizer` ile yönetilir. Kod içine sabit UI metni yazılmaz.

---

## 13. Dependency Politikası

Paket eklemeden önce kontrol et:

1. Framework bunu zaten sağlıyor mu?
2. Projede aynı işi yapan bir paket var mı?
3. Lisans uygun mu? (Ticari lisansa geçen paketlere dikkat et.)

Küçük bir ihtiyaç için ağır bir paket ekleme. Major framework, runtime veya paket yükseltmesinden önce kullanıcıyı bilgilendir.

---

## 14. Git

- Kullanıcı onayı olmadan destructive komut çalıştırılmaz: `reset --hard`, `clean -fd`, `push --force`, `checkout -- .`, branch silme. Kullanıcının commit edilmemiş değişiklikleri geri alınmaz ve üzerine yazılmaz.
- **Branch düzeni:** `dev` günlük çalışma, `main` canlı sürümdür. Başka kalıcı branch (`master`, `develop`, `prod` vb.) açılmaz. Çalışma her zaman `dev` üzerinde yapılır; işe başlamadan önce aktif branch kontrol edilir.
- `main`'e doğrudan commit veya push yapılmaz. `dev` → `main` aktarımı yalnızca kullanıcının açtığı veya onayladığı Merge Request ile olur.
- Projede `master` varsa kullanıcıya bildirilir. Yeniden adlandırma ve eski branch'in silinmesi onay alınmadan yapılmaz.
- Commit mesajları Conventional Commits formatında olur (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`).
- Commit veya push öncesi: build ve testler geçer, diff gözden geçirilir, **secret ve DB dosyası (`*.db`, `*.sqlite`, `*.mdf`) dahil edilmemiştir.**

---

## 15. Doğrulama

```bash
dotnet build          # Her değişiklikten sonra
dotnet test           # Test projesi varsa
```

**Uygulamayı çalıştırma:** Port seçilmez, `Properties/launchSettings.json` içindeki `https` profili kullanılır (`dotnet run --launch-profile https`).

**Test araçları:** xUnit, bUnit (component), `WebApplicationFactory` (integration). Integration testleri gerçek bir provider kullanır (SQLite veya Testcontainers). EF Core InMemory provider kullanılmaz.

**Definition of Done:** Bir iş, kendisini ilgilendiren maddeler doğrulanmadan bitmiş sayılmaz:

- [ ] Build hatasız geçer, testler geçer.
- [ ] Happy path ve hata senaryosu çalışır. Validation (required / invalid / valid / duplicate) kontrol edilmiştir.
- [ ] Loading, empty ve error durumları çalışır.
- [ ] CRUD, sorting, pagination ve filter (varsa) test edilmiştir.
- [ ] Authorization kontrol edilmiştir: yetkili, yetkisiz ve role/policy eksik kullanıcı.
- [ ] Responsive görünüm (mobile / tablet / desktop) kontrol edilmiştir.
- [ ] Beklenmeyen console hatası veya server exception yoktur. İlgili mevcut özellikler bozulmamıştır.
- [ ] Dış API çağrıları fake veya sandbox ile test edilmiştir.
- [ ] Dışa açık API varsa breaking change yapılmamıştır (veya yeni versiyon açılmıştır) ve OpenAPI dokümanı günceldir.
- [ ] Kök dizin ve `docs/` düzeni §4'e uygundur (kökte fazladan klasör veya `.md` dosyası yoktur).
- [ ] Secret eklenmemiştir. **Production DB'ye ve canlı dış servislere yazma yapılmamıştır.**

Bir adım ortam nedeniyle çalıştırılamadıysa bu açıkça belirtilir.

---

## 16. Raporlama

Görev veya faz sonunda bu format kullanılır. Kısa tutulur, aynı bilgi tekrarlanmaz. Token tasarrufu için güvenlik, doğruluk veya testten ödün verilmez.

```text
TAMAMLANDI  (veya: FAZ n TAMAMLANDI)

Yapılanlar:        - ...
Değişen dosyalar:  - ...
Build / Test:      Başarılı | Başarısız | Çalıştırılamadı (neden)
Database:          Local: Var/Yok · Production: YOK
Dış servis:        Sandbox/Fake · Canlı ortama yazma: YOK
API contract:      Değişmedi | Non-breaking | Yeni versiyon (vN)
Bilinen sorunlar:  - ...
Sonraki adım:      - ...
```
