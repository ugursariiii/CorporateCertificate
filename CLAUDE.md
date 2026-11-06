@AGENTS.md
@docs/MIMARI.md

<!-- Ortak kurallar AGENTS.md dosyasındadır. Buraya yalnızca Claude Code'a özgü notlar eklenir. -->

## Claude Code notları

- Uygulamayı (`python src/main.py`) çalıştırmak **production MSSQL sunucusuna bağlanır**; yerel/test veritabanı yoktur. Kullanıcı açıkça istemedikçe uygulamayı çalıştırma, DB'ye sorgu atma (AGENTS.md §9).
- Doğrulama için `python -m unittest discover -s tests` ve `python -m py_compile src/main.py` yeterlidir; ikisi de DB'ye bağlanmaz.
- Paylaşılan ağ klasörüne (`\172.16.0.201\...`) yazma da canlı ortama yazmadır (AGENTS.md §11.5).
