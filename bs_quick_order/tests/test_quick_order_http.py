# -*- coding: utf-8 -*-
"""The page and the form, fetched the way a browser fetches them.

The form is posted with its own CSRF token, read out of the page the test just
rendered: turning CSRF off would have made these tests shorter and the module
wrong, and a token the test cannot obtain is a token a customer's browser
cannot obtain either.
"""
import re

from odoo.tests.common import HttpCase, tagged

PAGE = "/shop/quick-order"
CSRF_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')


@tagged("post_install", "-at_install")
class TestQuickOrderHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.widget = cls._product("WIDGET-01", 10.0)
        cls.box = cls._product("BOX-6", 4.0)
        cls.portal = cls._portal_user("quick_order_portal", "quick_order_pw")

    @classmethod
    def _product(cls, reference, price):
        return cls.env["product.template"].create({
            "name": reference,
            "type": "consu",
            "sale_ok": True,
            "is_published": True,
            "default_code": reference,
            "list_price": price,
            "taxes_id": [(6, 0, [])],
        }).product_variant_id

    @classmethod
    def _portal_user(cls, login, password):
        user = cls.env["res.users"].create({
            "name": login,
            "login": login,
            "email": "%s@example.com" % login,
            "password": password,
        })
        # 20 renamed the field; 16 to 19 still call it groups_id.
        field = "group_ids" if "group_ids" in user._fields else "groups_id"
        user.write({field: [(6, 0, [cls.env.ref("base.group_portal").id])]})
        return user

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _token(self, url=PAGE):
        page = self.url_open(url)
        self.assertEqual(page.status_code, 200, "the form page did not render")
        found = CSRF_RE.search(page.text)
        self.assertTrue(found, "the page carries no csrf token")
        return found.group(1)

    def _submit(self, lines, token=None):
        return self.url_open(PAGE, data={
            "csrf_token": token if token is not None else self._token(),
            "lines": lines,
        })

    def _cart(self):
        order = self.env["sale.order"].search([
            ("partner_id", "=", self.portal.partner_id.id),
            ("state", "=", "draft"),
        ], limit=1)
        return order

    def _quantities(self):
        return {line.product_id.default_code: line.product_uom_qty
                for line in self._cart().order_line}

    # ------------------------------------------------------------------
    # Who gets the form
    # ------------------------------------------------------------------
    def test_an_anonymous_visitor_is_sent_to_the_login_page(self):
        self.authenticate(None, None)
        response = self.url_open(PAGE, allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        location = response.headers.get("Location", "")
        self.assertIn("/web/login", location)
        self.assertIn("quick-order", location, "the login must lead back here")

    def test_a_signed_in_customer_gets_the_form(self):
        self.authenticate(self.portal.login, "quick_order_pw")
        page = self.url_open(PAGE)
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="o_wsqo_form"', page.text)
        self.assertIn('name="lines"', page.text)
        self.assertIn('name="csrf_token"', page.text)
        # the form posts back to the page it was rendered on
        self.assertIn('action="/shop/quick-order"', page.text)

    def test_the_shop_header_links_to_the_page(self):
        self.authenticate(self.portal.login, "quick_order_pw")
        page = self.url_open("/shop")
        self.assertEqual(page.status_code, 200)
        self.assertIn('href="/shop/quick-order"', page.text)

    # ------------------------------------------------------------------
    # What the form does
    # ------------------------------------------------------------------
    def test_a_post_adds_the_lines_to_the_cart(self):
        self.authenticate(self.portal.login, "quick_order_pw")
        page = self._submit("WIDGET-01 2\nBOX-6 3")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="o_wsqo_added"', page.text)
        self.assertIn("2 lines were added", page.text)
        self.assertEqual(self._quantities(), {"WIDGET-01": 2.0, "BOX-6": 3.0})
        self.assertEqual(self._cart().amount_untaxed, 32.0)

    def test_a_post_with_one_typo_keeps_the_other_lines(self):
        self.authenticate(self.portal.login, "quick_order_pw")
        page = self._submit("WIDGET-01 2\nNOPE 1\nBOX-6 3")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="o_wsqo_errors"', page.text)
        self.assertIn("No product matches this reference", page.text)
        # the answer quotes the number of the line in the customer's own text
        self.assertIn("Line 2", page.text)
        self.assertEqual(self._quantities(), {"WIDGET-01": 2.0, "BOX-6": 3.0})

    def test_a_post_of_nothing_but_typos_adds_nothing(self):
        """Negative control: the page says so and the cart stays empty."""
        self.authenticate(self.portal.login, "quick_order_pw")
        page = self._submit("NOPE 1")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Nothing was added to your cart", page.text)
        self.assertIn("No product matches this reference", page.text)
        self.assertFalse(self._cart().order_line)

    def test_a_post_without_a_token_is_refused(self):
        """CSRF is on: the form is not a hole in the shop's own protection."""
        self.authenticate(self.portal.login, "quick_order_pw")
        page = self.url_open(PAGE, data={"lines": "WIDGET-01 2"})
        self.assertEqual(page.status_code, 400)
        self.assertFalse(self._cart().order_line)

    def test_a_list_over_the_cap_is_refused_as_a_whole(self):
        self.authenticate(self.portal.login, "quick_order_pw")
        lines = "\n".join("SKU-%03d 1" % index for index in range(101))
        page = self._submit(lines)
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="o_wsqo_error"', page.text)
        self.assertIn("limited to 100 lines", page.text)
        self.assertFalse(self._cart().order_line)
