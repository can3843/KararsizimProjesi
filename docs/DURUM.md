# Kararsızım — Güncel Durum ve Devir Notu

> Yeni bir oturum açan herkes (insan ya da Claude) önce `docs/PROJECT.md` (şartname), sonra bu dosyayı okur.
> Bu dosyada **parola, anahtar veya bağlantı adresi yoktur**; gizli değerler yalnızca yerel `.env` ve Vercel ortam değişkenlerindedir.
> Son güncelleme: 2026-10-04, Faz 6 sonrası. Uygulama **canlıda**: https://kararsizim-app.vercel.app. Sıradaki iş: Faz 7 (opsiyonel) ve Faz 6'nın açık kalan tek maddesi (soğuk başlangıç kontrolü, aşağıda).

## 1. Nerede kaldık

| Faz | Durum | Commit |
|---|---|---|
| 0 İskelet | bitti | `6b37c59` |
| 1 Veri modeli + Supabase | bitti | `da1ad1c` |
| 2 Kimlik doğrulama | bitti | `45803ef` |
| 3 Anket oluşturma ve akış | bitti | `339871c` |
| 4 Oylama ve sonuçlar | bitti | `e8abcf4` |
| 5 Arayüz cilası | bitti | `7fec02c` |
| 6 Vercel deployment | bitti (soğuk başlangıç kontrolü hariç, bkz. Bölüm 4) | `555ab9b` |
| 7 Sertleştirme (opsiyonel) | başlanmadı | — |

- Depo: https://github.com/can3843/KararsizimProjesi.git, dal `main`, tümü pushlanmış, çalışma ağacı temiz.
- Canlı: Vercel projesi `kararsizim-app` (ekip `Ayhancan`, Hobby), GitHub'a bağlı; `main`'e her push production'a otomatik deploy olur. Adres https://kararsizim-app.vercel.app, bölge `fra1`.
- Testler: `python manage.py test` → **168 test, hepsi geçiyor**. Zorunlu testlerin (Bölüm 9) hepsi var.
- Lighthouse Accessibility: 9 sayfa türünün hepsi **100** (Faz 5'te `npx lighthouse` ile ölçüldü; projeye eklenmedi).
- Faz 0–5'in tüm kabul kriterleri kapandı.

## 2. Yerelde çalıştırma

```powershell
.\.venv\Scripts\python.exe manage.py runserver        # http://127.0.0.1:8000/
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py seed_demo --reset  # yerel demo veri (kullanıcıların parolası yok; --password ile verilebilir)
```

- Python 3.14.4, Django 6.1.1 (`requirements.txt` şartnamedeki gibi, yeni bağımlılık eklenmedi).
- Yerel `.env` şu an `DJANGO_DEBUG=False` (kullanıcı canlıya benzer denemek istedi). `DEBUG=False` iken statikler WhiteNoise'dan gelir: `python manage.py collectstatic --noinput` çalıştırılmalı, statik dosya değişince tekrar. `staticfiles/` git'te yoktur.
- `DATABASE_URL` boşsa yerel SQLite (`db.sqlite3`, git'te yok). Yerelde demo veri ve kullanıcının kendi hesabı (`ayhancan`) var.
- `.env.example` kullanıcının isteğiyle `DJANGO_DEBUG=False` içeriyor.

## 3. Supabase (veritabanı)

- Proje: `kararsizim`, ref `jrhedpisaeebxuknnfgu`, organizasyon `hqidbfkdnxeezjztmyls` (free plan), bölge `eu-central-1` (Frankfurt).
- **Pooler adresi `aws-1-eu-central-1.pooler.supabase.com`** (şartnamedeki `aws-0` bu proje için çalışmıyor). Transaction pooler `:6543`, Session pooler `:5432`; kullanıcı `postgres.<ref>`.
- Yerel `.env`'de `DATABASE_URL_DIRECT` (5432, migration için) dolu; `DATABASE_URL` (6543) yorum satırı. Parola kullanıcıda; sohbete yazılmadı.
- Şema uygulandı (Faz 1 migration'ları), tablolar: `accounts_user`, `polls_poll`, `polls_option`, `polls_vote` + Django tabloları.
- **RLS tüm tablolarda politikasız (deny-all) açık** (Supabase REST API `public` şemasını herkese açtığı için). Django `postgres` rolüyle bağlanır, etkilenmez. **Her yeni tablodan sonra** aynısı uygulanıp `get_advisors` ile kontrol edilmeli. "RLS Enabled No Policy" INFO uyarısı beklenendir.
- Supabase'de **demo veri var** (3 `demo_*` kullanıcı, 12 anket, ~445 oy). Kullanıcı kararıyla canlıda **bırakıldı**; canlı doğrulamada bir ankete bir oy eklendi.
- Migration'ı Windows'ta çalıştırma (`DATABASE_URL=$X python ...` PowerShell'de çalışmaz):
  ```powershell
  $env:DATABASE_URL = "<Session pooler adresi>"; .\.venv\Scripts\python.exe manage.py migrate; Remove-Item Env:DATABASE_URL
  ```
- Eşzamanlı çift oy Postgres üzerinde doğrulandı: 8 eşzamanlı istekten 1'i başarılı, 7'si 409, sayaç tam 1 artıyor.

## 4. Faz 6 — Vercel deployment (yapıldı)

Ayrıntılı rehber: `docs/DEPLOY.md`.

- **Ayarlar:** `settings.py` içinde `VERCEL=1` (Vercel tanımlar) iken HTTPS yönlendirmesi, güvenli çerezler ve `SECURE_PROXY_SSL_HEADER` açılır; `DJANGO_SECURE` ile ezilebilir. `config/test_settings.py` bunu test eder. `vercel.json` (`fra1`, `config/wsgi.py` için `maxDuration`) Vercel'in Django dokümanıyla doğrulandı. Statik depolama varsayılan bırakıldı (manifest depolama `500.html`'i riske atar).
- **Vercel projesi** dashboard'dan GitHub deposunun import edilmesiyle kuruldu. Vercel MCP bağlayıcısı proje oluşturamadı (403) ve projeyi göremiyor; deploy/env işlemleri kullanıcı tarafından panelden yapılır, gizli değerler sohbete girmedi.
- **Ortam değişkenleri** (değerler yalnızca Vercel panelinde): `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS=.vercel.app`, `DJANGO_SECRET_KEY`, `VOTER_KEY_SALT`, `DATABASE_URL` (Transaction pooler 6543), `DJANGO_CSRF_TRUSTED_ORIGINS=https://kararsizim-app.vercel.app`. Değişken eklenince yeniden deploy gerekir.
- **Canlı doğrulama (2026-10-04):** ana sayfa 200; `/static/...` Vercel CDN'den (`x-vercel-cache: HIT`); özel 404; `http`→`https` 308; CSRF çerezi `Secure`; anonim oy veritabanına yazıldı, sayfa yenilenince sonuç görünüyor, yüzdeler toplamı 100; girişsiz `/anket/olustur/` → `/giris/?next=`; `/sonuc/` JSON'unda e-posta yok. Kayıt, giriş ve anket oluşturma kullanıcı tarafından canlıda denendi, çalışıyor.
- **Açık kalan tek madde:** soğuk başlangıçtan sonraki ilk isteğin 500 vermediği henüz ölçülmedi (birkaç saat bekleyip siteyi açmak yeterli). Faz 6'nın diğer kabul kriterleri kapandı.
- `vercel dev` ve Vercel CLI kullanılmadı (projeye eklenmedi); canlıya benzer doğrulama deploy ile yapıldı.
- HSTS (`SECURE_HSTS_SECONDS`) Django'da ayarlanmadı; Vercel kendi `Strict-Transport-Security` başlığını gönderiyor.

## 5. Önemli kararlar ve şartnameden sapmalar (ayrıntı `PROJECT.md` içinde işlendi)

- **Sonuç görünürlüğü**: karar çubuğu ve kararsızlık rozeti herkese açık; yüzde rakamları oy sonrası, anket kapanınca veya sahibi için görünür. `/sonuc/` JSON'unda gizli sayılar `null`. Rozet farkı en çok oy alan iki seçenek arasında.
- **Giriş**: kullanıcı adı + parola, büyük/küçük harf duyarsız. Kullanıcı adı için DB'de `Lower(username)` benzersizlik kısıtı da var.
- **Oy arayüzü**: radyo + ayrı "Oy ver" butonu (oy geri alınamaz). JS'siz hata durumları aynı kodla (400/403/409) sayfa render eder.
- **Günlük 10 anket sınırı**: İstanbul saatine göre gece yarısından başlar.
- **Hata/tehlike rengi**: `--danger` beyazda 4.5:1 vermez; metin `--ink`, işaret `--danger`. Odak halkasına koyu iç halka eklendi.
- **Ham hex** yalnızca `tokens.css` ve `logo.svg` / `og-image.png` içinde.
- Şartnamede olmayan eklenenler: `403.html`, `403_csrf.html`, `submit-lock.js`, `partials/form_field.html`, `decision_bar.html`, `poll_list.html`, `confirm_delete.html`, `test_voting.py`, `test_ui.py`.

## 6. Bilinen sınırlar (kabul edilmiş)

- Çerezini temizleyen anonim ziyaretçi tekrar oy verebilir; anonim oy verip giriş yapan kullanıcı bir kez daha oy verebilir. Faz 7'de IP tabanlı hız sınırıyla hafifletilecek (ham IP saklanmaz).
- JS için otomatik test altyapısı yok (şartname ayrı test framework'ü yasaklıyor); JS değişiklikleri tarayıcıda elle doğrulanır (Faz 5'te böyle bir hata yakalanıp düzeltildi).
- `og-image.png` yalnızca marka çubuğunu gösterir (metin yok).
- Faz 7 maddeleri (hız sınırı, paylaş butonu, arama, rapor, `closes_at` formu vb.) yapılmadı.

## 7. Çalışma biçimi ve küçük tuzaklar

Kullanıcıyla çalışma şekli:
- Fazlar sırayla; her faza başlamadan kısa özet, bitince kabul kriterlerini tek tek işaretleyen özet. Şartnamayla çelişki varsa **uygulamadan önce** sor.
- Commit/push yalnızca kullanıcı isteyince; mesaj `feat: faz N — ...` biçiminde, sonuna `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Arayüz metinleri Türkçe, kod İngilizce. Yeni bağımlılık eklenmez (önce sorulur).
- Kullanıcı bir fazı canlı sunucuda kendisi inceler; sunucu linkini ver.

Teknik tuzaklar (Windows + PowerShell 5.1):
- `git commit -m @'...'@` içinde çift tırnak varsa argüman bölünür; commit mesajını dosyaya yazıp `git commit -F` kullan.
- Yerel komutların stderr çıktısı PowerShell'de sahte `NativeCommandError` üretir (`git push` çıkış kodu 255 görünebilir); gerçek sonuç `main -> main` satırındadır.
- Betikleri `manage.py shell`'e boru ile verme; `manage.py shell -c "exec(open(r'...', encoding='utf-8').read())"` kullan.
- Çok sayıda eşzamanlı yeni bağlantıda Windows DNS çözümlemesi geçici hata verebilir (`Errno 11001`); yeniden dene.
- Django `X-Frame-Options: DENY` yolladığı için sayfalar iframe'e yüklenmez (test araçlarında beklenen).
- Testlerde WhiteNoise "staticfiles dizini yok" uyarısı zararsızdır.

## 8. Yeni oturum için başlangıç komutu

> `docs/PROJECT.md` ve `docs/DURUM.md` dosyalarını oku. Faz 7'den (sertleştirme, opsiyonel) hangi maddelerle devam edeceğimizi öner; başlamadan önce ne yapacağını özetle. `main`'e her push canlıya otomatik deploy olur: push, ortam değişkeni ve alan adı gibi dışarıya açık adımlarda onayımı iste.
