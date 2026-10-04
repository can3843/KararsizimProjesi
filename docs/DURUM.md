# Kararsızım — Güncel Durum ve Devir Notu

> Yeni bir oturum açan herkes (insan ya da Claude) önce `docs/PROJECT.md` (şartname), sonra bu dosyayı okur.
> Bu dosyada **parola, anahtar veya bağlantı adresi yoktur**; gizli değerler yalnızca yerel `.env` ve Vercel ortam değişkenlerindedir.
> Son güncelleme: 2026-10-04, Faz 6 sonrası. Uygulama **canlıda**: https://kararsizim-app.vercel.app. Tüm fazlar bitti; Faz 6'nın açık kalan tek maddesi soğuk başlangıç kontrolü (Bölüm 4).

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
| 6.1 Güvenlik incelemesi düzeltmeleri (hız sınırı, bildirim) | bitti, canlıda (Bölüm 9) | `cf06177` |
| 7 Sertleştirme ve küçük eklemeler | bitti (Bölüm 10) | bkz. git log |

- Depo: https://github.com/can3843/KararsizimProjesi.git, dal `main`, tümü pushlanmış, çalışma ağacı temiz.
- Canlı: Vercel projesi `kararsizim-app` (ekip `Ayhancan`, Hobby), GitHub'a bağlı; `main`'e her push production'a otomatik deploy olur. Adres https://kararsizim-app.vercel.app, bölge `fra1`.
- Testler: `python manage.py test` → **223 test, hepsi geçiyor** (Faz 7 sonrası). Zorunlu testlerin (Bölüm 9) hepsi var.
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

- Çerezini temizleyen anonim ziyaretçi tekrar oy verebilir; anonim oy verip giriş yapan kullanıcı bir kez daha oy verebilir. Faz 6.1'de IP tabanlı hız sınırıyla hafifletildi (Bölüm 9); tamamen kapanmadı.
- JS için otomatik test altyapısı yok (şartname ayrı test framework'ü yasaklıyor); JS değişiklikleri tarayıcıda elle doğrulanır (Faz 5'te böyle bir hata yakalanıp düzeltildi).
- `og-image.png` yalnızca marka çubuğunu gösterir (metin yok).
- Faz 7 maddeleri yapıldı (Bölüm 10).

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

> `docs/PROJECT.md` ve `docs/DURUM.md` dosyalarını oku. Tüm fazlar bitti; yalnızca Faz 6'nın soğuk başlangıç kontrolü ve istersen Faz 7 sonrası Lighthouse ölçümü kaldı. `main`'e her push canlıya otomatik deploy olur: push, ortam değişkeni ve alan adı gibi dışarıya açık adımlarda onayımı iste.

## 9. Faz 6.1 — Güvenlik incelemesi düzeltmeleri

`code-review-security` incelemesindeki üç bulgu kapatıldı. Ham IP/kullanıcı adı saklanmaz; `ratelimit_ratelimithit.scope` tuzlu SHA-256 özetidir.

- **Yeni uygulama `ratelimit`**: `RateLimitHit` tablosu, `limits.py` (tüm sınırlar tek yerde), `services.py` (`client_ip`, `is_limited`, `record`, fırsatçı temizlik: eski olaylar ve süresi dolmuş oturumlar), `LoginRateLimitMiddleware`. Vercel'de IP `X-Vercel-Forwarded-For` başlığından okunur; IPv6 /64 bloğu tek sayılır.
- **Anonim oy**: IP başına saatte 60 deneme (oturum yaratılmadan önce denetlenir) ve aynı ankete 24 saatte 5 anonim oy; aşılınca 429. Doğrulama: aynı CSRF çiftiyle 200 çerezsiz istek önceden 200 oy + 200 oturum satırıydı, şimdi 5 + 5. Oturum açmış kullanıcılar bu sınırlara tabi değil. Ortak IP'li (okul, mobil operatör) kullanıcılar için sınırlar bilerek cömert.
- **Giriş/kayıt/admin**: başarısız giriş IP başına 20, kullanıcı adı başına 8 (15 dk); admin girişi IP başına 10 (15 dk); kayıt IP başına 5 / 24 saat. 429 sayfası `templates/429.html`. Bilinen yan etki: bir kullanıcı adını kasıtlı kilitleyerek hesabı 15 dk kullanılamaz yapmak mümkün.
- **Spam/moderasyon**: anket oluşturma IP başına 24 saatte 20 (anket silmek sayacı sıfırlamaz); anket detayında oturum açmış başka kullanıcılar için "Bu anketi bildir" (`Report` modeli, kullanıcı başına anket başına tek bildirim, günde 10); admin'de `Poll` listesinde bildirim sayısı, bildirim satır içi listesi, `Report` listesi ve "Seçili anketleri kapat" eylemi. Otomatik gizleme ve e-posta doğrulaması yapılmadı.
- `VOTER_KEY_SALT` production'da (DEBUG kapalıyken) tanımsızsa uygulama açılmaz.
- **Migration'lar:** `ratelimit/0001_initial`, `polls/0002_report`. İki yeni tabloda RLS açık olmalı (Bölüm 3). Canlıda tablolar Supabase MCP ile elle oluşturuldu (RLS açık, `django_migrations` kayıtları eklendi), sonra push edildi. **Sıra önemli:** yeni tablo içeren bir değişiklikte önce tablolar canlı veritabanında oluşturulmalı, sonra `main` push edilmeli; yoksa canlıda 500 verir. Canlı doğrulama (2026-10-04): admin girişinde 10 deneme geçti, 11.si 429; ana sayfa, anket, `/sonuc/`, giriş, kayıt sayfaları 200; `get_advisors` yalnızca beklenen "RLS Enabled No Policy" INFO uyarısını veriyor.

## 10. Faz 7 — Sertleştirme ve küçük eklemeler (yapıldı)

Şema değişikliği yok (yeni tablo/migration yok), canlı veritabanında işlem gerekmedi.

- **Hız sınırı + bildirim**: Bölüm 9'da (Faz 6.1).
- **Kayıt honeypot'u**: `RegisterForm.website` gizli alanı (ekran dışı, `aria-hidden`, `tabindex=-1`); doluysa kayıt reddedilir.
- **Paylaş butonu** (`static/js/share.js`): `navigator.share`, yoksa panoya kopyalama. JS kapalıyken buton gizli kalır.
- **Arama**: anasayfada `?q=` ile soru içinde `icontains` araması (en çok 100 karakter); sekmeler ve "Daha fazla göster" sorguyu korur.
- **Kararsızlık kartı** (`static/js/card.js`): sonuçlar görünürken 1200×630 PNG üretir ve indirir; renkler CSS değişkenlerinden okunur. Oy verince sayfa yenilenmeden buton belirir. Tarayıcıda elle doğrulandı (otomatik JS testi yok, bkz. Bölüm 6).
- **`closes_at`**: anket formunda "Ne kadar açık kalsın?" (süresiz, 1 saat, 1/3/7 gün); süresi dolan anket okunurken tembel olarak `closed` yapılır (`services.close_if_expired`, cron yok); detayda "… tarihinde kapanır" görünür.
- **Testler**: `polls/test_phase7.py` (21 test), `ratelimit/tests.py`.
- Lighthouse Accessibility Faz 7 sonrası yeniden ölçülmedi.
