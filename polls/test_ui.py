import re
import struct
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import Client, TestCase
from django.urls import reverse

from .models import Poll
from .tests import PASSWORD, make_poll

User = get_user_model()

FOCUSABLE_INPUT_TYPES_WITHOUT_LABEL = {"hidden", "submit", "button"}


class PageAudit(HTMLParser):
    """Erişilebilirlik temellerini toplar: dil, ana bölge, başlıklar, etiketler, alt metinler."""

    def __init__(self):
        super().__init__()
        self.lang = None
        self.mains = 0
        self.h1s = 0
        self.title = ""
        self.ids = []
        self.label_targets = set()
        self.controls = []          # (tag, attrs)
        self.images_without_alt = 0
        self.nameless = []          # metni olmayan buton/bağlantı
        self._in_title = False
        self._stack = []            # açık buton/bağlantı: [tag, attrs, text]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.lang = attrs.get("lang")
        elif tag == "main":
            self.mains += 1
        elif tag == "h1":
            self.h1s += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "img" and "alt" not in attrs:
            self.images_without_alt += 1
        elif tag == "label" and attrs.get("for"):
            self.label_targets.add(attrs["for"])
        elif tag in ("input", "textarea", "select"):
            self.controls.append((tag, attrs))
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag in ("button", "a"):
            self._stack.append([tag, attrs, ""])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in ("button", "a") and self._stack:
            _, attrs, text = self._stack.pop()
            if not text.strip() and not attrs.get("aria-label"):
                self.nameless.append((tag, attrs))

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        for item in self._stack:
            item[2] += data


def audit(response):
    parser = PageAudit()
    parser.feed(response.content.decode())
    return parser


class AccessibilityBasicsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        cls.poll = make_poll(cls.author, counts=(3, 2, 1))
        cls.closed = make_poll(cls.author, "Kapalı anketin sorusu burada", counts=(1, 1), status=Poll.Status.CLOSED)

    def pages(self):
        owner = Client()
        owner.force_login(self.author)
        return {
            "index": self.client.get(reverse("polls:index")),
            "detail": self.client.get(self.poll.get_absolute_url()),
            "detail (closed)": self.client.get(self.closed.get_absolute_url()),
            "detail (owner)": owner.get(self.poll.get_absolute_url()),
            "create": owner.get(reverse("polls:create")),
            "delete": owner.get(reverse("polls:delete", args=[self.poll.public_id])),
            "profile": self.client.get(reverse("polls:profile", args=["ayse"])),
            "register": self.client.get(reverse("accounts:register")),
            "login": self.client.get(reverse("accounts:login")),
            "404": self.client.get("/yok/boyle/bir/sayfa/"),
        }

    def test_every_page_has_the_basics(self):
        for name, response in self.pages().items():
            with self.subTest(page=name):
                page = audit(response)
                self.assertEqual(page.lang, "tr")
                self.assertTrue(page.title.strip(), "boş <title>")
                self.assertEqual(page.mains, 1, "tek <main> olmalı")
                self.assertEqual(page.h1s, 1, "tek <h1> olmalı")
                self.assertEqual(page.images_without_alt, 0)
                self.assertEqual(page.nameless, [], "metni olmayan buton/bağlantı")
                self.assertEqual(len(page.ids), len(set(page.ids)), "yinelenen id")

    def test_every_form_control_has_a_label(self):
        for name, response in self.pages().items():
            with self.subTest(page=name):
                page = audit(response)
                for tag, attrs in page.controls:
                    if attrs.get("type") in FOCUSABLE_INPUT_TYPES_WITHOUT_LABEL:
                        continue
                    labelled = attrs.get("id") in page.label_targets or attrs.get("aria-label")
                    self.assertTrue(labelled, f"etiketsiz alan: {tag} {attrs}")

    def test_vote_radios_sit_inside_a_labelled_fieldset(self):
        content = self.client.get(self.poll.get_absolute_url()).content.decode()
        self.assertIn("<fieldset", content)
        self.assertIn("<legend", content)

    def test_results_region_is_a_polite_live_region(self):
        content = self.client.get(self.poll.get_absolute_url()).content.decode()
        self.assertIn('class="results-region" aria-live="polite"', content)

    def test_toast_region_is_a_polite_live_region(self):
        content = self.client.get(reverse("polls:index")).content.decode()
        self.assertIn('id="toast-region" class="toast-region" aria-live="polite"', content)

    def test_skip_link_targets_main(self):
        content = self.client.get(reverse("polls:index")).content.decode()
        self.assertIn('<a class="skip-link" href="#main">', content)
        self.assertIn('<main id="main"', content)

    def test_bar_has_a_text_alternative(self):
        content = self.client.get(self.poll.get_absolute_url()).content.decode()
        self.assertRegex(content, r'class="decision-bar" role="img" aria-label="[^"]+"')

    def test_color_is_never_the_only_signal_for_the_voters_choice(self):
        self.client.force_login(self.author)
        content = self.client.get(self.poll.get_absolute_url()).content.decode()
        self.assertIn('aria-label="Senin oyun"', content)


class MetaTagTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def test_site_wide_meta(self):
        content = self.client.get(reverse("polls:index")).content.decode()
        self.assertIn('<meta property="og:title" content="Kararsızım">', content)
        self.assertIn('<meta property="og:url" content="http://testserver/">', content)
        self.assertIn(
            '<meta property="og:image" content="http://testserver/static/img/og-image.png">', content
        )
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', content)
        self.assertIn('<link rel="icon" href="/static/img/logo.svg" type="image/svg+xml">', content)
        self.assertIn('<meta name="description"', content)

    def test_poll_page_puts_the_question_in_the_share_preview(self):
        poll = make_poll(self.author, "Pizza mı hamburger mi yesek?", counts=(2, 1))
        content = self.client.get(poll.get_absolute_url()).content.decode()
        self.assertIn('<meta property="og:title" content="Pizza mı hamburger mi yesek?">', content)
        self.assertIn("<title>Pizza mı hamburger mi yesek? · Kararsızım</title>", content)
        self.assertIn(f'content="http://testserver{poll.get_absolute_url()}"', content)
        self.assertIn('property="og:description" content="3 kişi oy verdi. Sen de oyunu kullan."', content)

    def test_poll_description_is_used_when_present(self):
        poll = make_poll(self.author, description="Akşam için karar veremedik")
        content = self.client.get(poll.get_absolute_url()).content.decode()
        self.assertIn('property="og:description" content="Akşam için karar veremedik"', content)

    def test_user_text_is_escaped_inside_meta_attributes(self):
        poll = make_poll(self.author, 'Şu "tırnak" & <etiket> var mı?')
        content = self.client.get(poll.get_absolute_url()).content.decode()
        self.assertIn(
            'property="og:title" content="Şu &quot;tırnak&quot; &amp; &lt;etiket&gt; var mı?"', content
        )
        self.assertNotIn("<etiket>", content)

    def test_fonts_are_loaded_with_preconnect_and_swap(self):
        content = self.client.get(reverse("polls:index")).content.decode()
        self.assertIn('<link rel="preconnect" href="https://fonts.googleapis.com">', content)
        self.assertIn('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>', content)
        for family in ("Bricolage+Grotesque:wght@700;800", "Inter:wght@400;500;600", "JetBrains+Mono:wght@500"):
            self.assertIn(family, content)
        self.assertIn("display=swap", content)

    def test_static_brand_assets_exist(self):
        self.assertIsNotNone(finders.find("img/logo.svg"))
        image_path = finders.find("img/og-image.png")
        self.assertIsNotNone(image_path)
        header = Path(image_path).read_bytes()[:24]
        self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", header[16:24]), (1200, 630))


class HeaderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)

    def test_logo_image_is_decorative(self):
        content = self.client.get(reverse("polls:index")).content.decode()
        self.assertIn('<img src="/static/img/logo.svg" alt=""', content)

    def test_authenticated_header_layout_and_profile_link(self):
        self.client.force_login(self.user)
        content = self.client.get(reverse("polls:index")).content.decode()
        self.assertIn("site-header__inner--authed", content)
        self.assertIn('<a class="site-header__user" href="/kullanici/ayse/">@ayse</a>', content)

    def test_anonymous_header_has_no_authenticated_modifier(self):
        content = self.client.get(reverse("polls:index")).content.decode()
        self.assertNotIn("site-header__inner--authed", content)


class SubmitLockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        cls.poll = make_poll(cls.author)

    def test_forms_that_change_data_lock_their_button(self):
        owner = Client()
        owner.force_login(self.author)
        pages = {
            "register": self.client.get(reverse("accounts:register")),
            "login": self.client.get(reverse("accounts:login")),
            "create": owner.get(reverse("polls:create")),
            "delete": owner.get(reverse("polls:delete", args=[self.poll.public_id])),
            "close": owner.get(self.poll.get_absolute_url()),
        }
        for name, response in pages.items():
            with self.subTest(page=name):
                self.assertContains(response, "data-submit-lock")
                self.assertContains(response, "data-loading-text")

    def test_script_is_loaded_site_wide(self):
        self.assertContains(self.client.get(reverse("polls:index")), "js/submit-lock.js")

    def test_vote_script_is_only_loaded_when_voting_is_possible(self):
        self.assertContains(self.client.get(self.poll.get_absolute_url()), "js/vote.js")
        closed = make_poll(self.author, "Kapalı anketin sorusu burada", status=Poll.Status.CLOSED)
        self.assertNotContains(self.client.get(closed.get_absolute_url()), "js/vote.js")


class ErrorPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = User.objects.create_user("ayse", "ayse@example.com", PASSWORD)
        cls.other = User.objects.create_user("mehmet", "mehmet@example.com", PASSWORD)
        cls.poll = make_poll(cls.author)

    def test_404_uses_the_site_template(self):
        response = self.client.get("/boyle/bir/sayfa/yok/")
        self.assertContains(response, "Bu sayfa yok", status_code=404)
        self.assertContains(response, "site-header", status_code=404)
        self.assertContains(response, "Ana sayfaya dön", status_code=404)

    def test_unknown_poll_and_profile_show_the_same_404(self):
        for url in ("/anket/yokboyleid/", "/kullanici/yok_boyle/"):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), "Bu sayfa yok", status_code=404)

    def test_403_for_non_owner_explains_what_to_do(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("polls:delete", args=[self.poll.public_id]))
        self.assertContains(response, "Bu işleme iznin yok", status_code=403)
        self.assertContains(response, "yalnızca sahibi", status_code=403)

    def test_csrf_failure_page(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("accounts:login"), {"username": "ayse", "password": PASSWORD})
        self.assertContains(response, "Oturum doğrulanamadı", status_code=403)
        self.assertContains(response, "Sayfayı yenileyip", status_code=403)

    def test_500_is_standalone_and_does_not_leak_details(self):
        client = Client(raise_request_exception=False)
        with patch("polls.views.selectors.feed", side_effect=RuntimeError("gizli ayrıntı")):
            with self.assertLogs("django.request", level="ERROR"):
                response = client.get(reverse("polls:index"))
        self.assertContains(response, "Sunucuda bir hata oluştu", status_code=500)
        self.assertContains(response, "css/tokens.css", status_code=500)
        self.assertNotContains(response, "site-header", status_code=500)
        self.assertNotContains(response, "gizli ayrıntı", status_code=500)

    def test_error_messages_do_not_apologise(self):
        for template in ("404.html", "403.html", "403_csrf.html", "500.html"):
            text = (Path(settings.BASE_DIR) / "templates" / template).read_text(encoding="utf-8").lower()
            for word in ("üzgünüz", "özür", "maalesef"):
                self.assertNotIn(word, text, f"{template}: '{word}'")


class DesignTokenDisciplineTests(TestCase):
    css_dir = Path(settings.BASE_DIR) / "static" / "css"
    templates_dir = Path(settings.BASE_DIR) / "templates"

    def test_no_raw_hex_colors_outside_tokens(self):
        hex_color = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
        files = [self.css_dir / "base.css", self.css_dir / "components.css", *self.templates_dir.rglob("*.html")]
        for path in files:
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                # Bağlantı çapaları (href="#main") renk değildir.
                text = re.sub(r'href="#[^"]*"', "", text)
                self.assertEqual(hex_color.findall(text), [])

    def test_type_scale_and_fonts_come_from_tokens(self):
        for name in ("base.css", "components.css"):
            text = (self.css_dir / name).read_text(encoding="utf-8")
            self.assertEqual(re.findall(r"font-size:\s*\d+px", text), [], name)
            self.assertNotIn("ui-monospace", text, name)

    def test_tokens_declare_the_three_font_families_and_the_scale(self):
        tokens = (self.css_dir / "tokens.css").read_text(encoding="utf-8")
        for needle in ("Bricolage Grotesque", '"Inter"', "JetBrains Mono"):
            self.assertIn(needle, tokens)
        for size in (12, 14, 16, 20, 26, 34, 44):
            self.assertIn(f"--fs-{size}: {size}px", tokens)

    def test_motion_is_switched_off_for_reduced_motion(self):
        text = (self.css_dir / "components.css").read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion: reduce)", text)

    def test_focus_ring_follows_the_spec(self):
        text = (self.css_dir / "base.css").read_text(encoding="utf-8")
        self.assertIn("outline: 3px solid var(--sun);", text)
        self.assertIn("outline-offset: 2px;", text)

    def test_touch_targets_are_at_least_44px(self):
        text = (self.css_dir / "components.css").read_text(encoding="utf-8")
        for selector in (".button", ".tab", ".field input", ".site-header__logo"):
            block = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{[^}]*\}", text)
            self.assertIsNotNone(block, selector)
            self.assertIn("min-height: 44px", block.group(0), selector)
