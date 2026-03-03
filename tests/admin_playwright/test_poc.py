import os
import unittest

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import LiveServerTestCase, override_settings
from django.urls import path

try:
    from axe_playwright_python.sync_playwright import Axe
    from playwright.sync_api import expect, sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

urlpatterns = [
    path("admin/", admin.site.urls),
]


@unittest.skipUnless(PLAYWRIGHT_AVAILABLE, "Playwright or Axe is not installed")
class PlaywrightTestCase(LiveServerTestCase):
    """
    Modern addClassCleanup for a state reset.
    """

    @classmethod
    def setUpClass(cls):
        cls._old_async_unsafe = os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE")
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        cls.addClassCleanup(cls._restore_async_unsafe)

        super().setUpClass()

        try:
            cls.playwright = sync_playwright().start()
            cls.addClassCleanup(cls.playwright.stop)

            cls.browser = cls.playwright.chromium.launch(headless=True)
            cls.addClassCleanup(cls.browser.close)

            cls.context = cls.browser.new_context()
            cls.addClassCleanup(cls.context.close)
        except Exception:
            super().tearDownClass()
            raise

    @classmethod
    def _restore_async_unsafe(cls):
        if cls._old_async_unsafe is None:
            os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
        else:
            os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = cls._old_async_unsafe

    def setUp(self):
        self.page = self.context.new_page()
        self.addCleanup(self.page.close)

    def assertNoAccessibilityViolations(self, axe_options=None):
        results = Axe().run(self.page, options=axe_options)
        self.assertEqual(
            results.violations_count,
            0,
            f"Accessibility violations found:\n{results.generate_report()}",
        )


@override_settings(ROOT_URLCONF=__name__)
class TestAdminPlaywrightMigration(PlaywrightTestCase):
    available_apps = [
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
    ]

    def setUp(self):
        super().setUp()
        User.objects.create_superuser("admin", "admin@example.com", "password")

    def test_admin_login_and_accessibility(self):
        self.page.goto(f"{self.live_server_url}/admin/")
        self.assertNoAccessibilityViolations(
            axe_options={
                "rules": {
                    "page-has-heading-one": {"enabled": False},
                    "region": {"enabled": False},
                }
            }
        )
        self.page.locator('input[name="username"]').fill("admin")
        self.page.locator('input[name="password"]').fill("password")
        self.page.locator('input[type="submit"]').click()
        expect(self.page.locator("#content h1")).to_have_text("Site administration")
        self.assertNoAccessibilityViolations()
