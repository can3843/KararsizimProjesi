# Kararsızım — Deployment Rehberi (Vercel + Supabase)

Bu dosyada parola, anahtar veya bağlantı adresi **yoktur**; gizli değerler yalnızca Vercel proje ayarlarında ve yerel `.env` içinde durur.

## 1. Nasıl çalışıyor

- Vercel repoda `manage.py` dosyasını bulur ve `config/settings.py` içindeki `WSGI_APPLICATION` ayarından giriş noktasını çıkarır. Sarmalayıcı dosya veya `builds`/`routes` yazılmaz.
- `STATIC_ROOT` tanımlı olduğu için `collectstatic` build sırasında otomatik çalışır; statik dosyalar Vercel CDN'den gelir.
- `vercel.json` yalnızca `regions: ["fra1"]` (Supabase Frankfurt'ta) ve `config/wsgi.py` için `maxDuration` içerir.
- Deploy GitHub'a bağlıdır: `main`'e push → production, diğer dallar → preview.
- `VERCEL=1` ortam değişkeni Vercel'de otomatik vardır; `settings.py` bunu görünce HTTPS yönlendirmesini, güvenli çerezleri ve `SECURE_PROXY_SSL_HEADER`'ı açar. Yerelde kapatmak/açmak için `DJANGO_SECURE=False/True`. `DJANGO_SECURE` açıkken `DJANGO_DEBUG` kapalı olmak zorundadır.

## 2. Ortam değişkenleri (Vercel → Settings → Environment Variables)

| Değişken | Değer | Gizli mi? |
|---|---|---|
| `DJANGO_SECRET_KEY` | yeni, rastgele, yerelden farklı | **evet** |
| `VOTER_KEY_SALT` | yeni, rastgele, yerelden farklı | **evet** |
| `DATABASE_URL` | Supabase **Transaction pooler** (`:6543`) adresi | **evet** |
| `DJANGO_DEBUG` | `False` | hayır |
| `DJANGO_ALLOWED_HOSTS` | `.vercel.app` (özel alan adı eklenirse onu da) | hayır |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://<proje>.vercel.app` (virgülle birden fazla) | hayır |

Rastgele değer üretmek:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(50))"
```

Değişkeni değiştirdikten sonra mevcut deployment'a yansımaz; yeniden deploy gerekir.

`DATABASE_URL` adresi Supabase dashboard → **Connect** → Transaction pooler ekranından alınır (bu proje için önek `aws-1-eu-central-1`). Parolada yalnızca harf ve rakam kullan.

## 3. Migration (yerelden, Session pooler ile)

Migration'lar Vercel build sırasında **çalışmaz**. Yerel `.env` içindeki `DATABASE_URL_DIRECT` (Session pooler, `:5432`) kullanılır. PowerShell'de:

```powershell
$env:DATABASE_URL = "<Session pooler adresi>"; .\.venv\Scripts\python.exe manage.py migrate; Remove-Item Env:DATABASE_URL
```

Transaction pooler (`:6543`) ile migration çalıştırma; patlar.

Model değişince: `makemigrations` → commit → migration'ı yukarıdaki gibi uygula → **yeni tablolara RLS aç** (`ALTER TABLE "public"."<tablo>" ENABLE ROW LEVEL SECURITY;`) ve Supabase `get_advisors` ile kontrol et. "RLS Enabled No Policy" INFO uyarısı beklenendir.

## 4. Yönetici hesabı (opsiyonel)

```powershell
$env:DATABASE_URL = "<Session pooler adresi>"; .\.venv\Scripts\python.exe manage.py createsuperuser; Remove-Item Env:DATABASE_URL
```

Güçlü parola kullan; `/admin/` canlıda açıktır.

## 5. Yerelde canlıya benzer deneme

```powershell
$env:DJANGO_DEBUG="False"; .\.venv\Scripts\python.exe manage.py collectstatic --noinput; .\.venv\Scripts\python.exe manage.py runserver
```

`vercel dev` kullanılmaz (Vercel CLI projeye eklenmedi); canlıya benzer doğrulama preview deployment ile yapılır.

## 6. Sorun giderme

- **400 Bad Request (DisallowedHost):** `DJANGO_ALLOWED_HOSTS` içinde istek adresi yok.
- **403 CSRF doğrulaması başarısız:** `DJANGO_CSRF_TRUSTED_ORIGINS` içinde `https://` önekli tam adres yok.
- **Sonsuz yönlendirme:** `SECURE_PROXY_SSL_HEADER` çalışmıyor; `VERCEL=1` ve proxy başlığı kontrol edilir.
- **Bağlantı hatası / `prepared statement` hatası:** `DATABASE_URL` Transaction pooler (`:6543`) olmalı; doğrudan `db.<ref>.supabase.co` adresi Vercel'den ulaşılamaz (yalnızca IPv6).
- **Build hatası:** önce Vercel build günlüğüne bak; tahminle `vercel.json` doldurma. Güncel doküman: `vercel.com/docs/frameworks/full-stack/django`.
- **HSTS:** `SECURE_HSTS_SECONDS` bilerek ayarlı değil; tarayıcıda kalıcı olduğu için canlı HTTPS doğrulandıktan sonra düşük değerle (ör. 3600) açılması düşünülür.
