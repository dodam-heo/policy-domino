"""Verify generated routes are byte-for-byte identical to shared template."""
import unittest
from v4.classic_pages import (
    ROOT, TEMPLATE, DATA_URL_BY_ROUTE, render_page, TOKEN
)


class AgencyPageTests(unittest.TestCase):
    def test_both_routes_are_generated_from_shared_template(self):
        for route, url in DATA_URL_BY_ROUTE.items():
            with self.subTest(route=route):
                target = ROOT / "site" / route / "index.html"
                self.assertEqual(target.read_text("utf-8"), render_page(route))
                self.assertIn(f'data-policy-data-url="{url}"', render_page(route))

    def test_template_has_single_configuration_point(self):
        template = TEMPLATE.read_text("utf-8")
        self.assertEqual(template.count(TOKEN), 1)
        self.assertIn('class="chip active" data-law="high-impact"', template)
        self.assertNotIn("<style>", template)
        self.assertNotIn("<script>", template)
        self.assertIn("../assets/impact-model.js", template)
        self.assertIn("../assets/classic.js", template)

    def test_unknown_routes_not_emitted(self):
        with self.assertRaises(ValueError):
            render_page("unknown")


if __name__ == "__main__":
    unittest.main()
