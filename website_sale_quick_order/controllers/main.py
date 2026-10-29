# -*- coding: utf-8 -*-
"""The bulk order page: one form, one textarea, one answer.

The page is an ordinary form rather than a JSON endpoint on purpose. The
customer is signed in, the payload is a blob of text, and the answer is a page
that lists what happened line by line -- a redirect would throw that list away
and a JSON answer would have to rebuild the shop's markup in JavaScript. CSRF
stays on: the token is rendered in the form and posted back like any other
form of the site.

Only signed-in customers see the form, because a bulk order is an account
affair and because ``auth="user"`` already sends everybody else to the login
page with the page they asked for.
"""
from odoo import http
from odoo.http import request

from ..models.quick_order import (
    MAX_LINES,
    TOO_MANY_LINES,
    build_summary,
    message,
    parse_order_text,
)

TEMPLATE = "website_sale_quick_order.quick_order_page"


class WebsiteSaleQuickOrder(http.Controller):

    # ------------------------------------------------------------------
    # What the answer is built on
    # ------------------------------------------------------------------
    def _qo_website(self):
        """The site the request was routed to, put there by the website layer."""
        return request.website

    def _qo_cart(self):
        """The cart of the session, created on first use.

        19.0 moved the cart to ``request.cart``, which is a cache of the
        session's order and is *empty* until something creates it: the core
        add-to-cart routes write ``request.cart or request.website._create_cart()``,
        and so does this page.
        """
        return request.cart or request.website._create_cart()

    def _qo_pricelist(self):
        """The pricelist the cart is priced with, read the way the shop does.

        19.0 stopped asking the website for the pricelist: the website layer
        resolves it once per request and stores it on ``request.pricelist``.
        """
        return request.pricelist

    def _qo_values(self, lines="", result=None, error=None):
        return {
            "website": self._qo_website(),
            "lines": lines,
            "result": result,
            "error": error,
            "max_lines": MAX_LINES,
            # The URL the form posts back to: the one the customer is on, so
            # a translated page answers in its own language.
            "form_action": request.httprequest.path,
        }

    # ------------------------------------------------------------------
    # The page
    # ------------------------------------------------------------------
    @http.route("/shop/quick-order", type="http", auth="user", website=True,
                methods=["GET"], sitemap=False)
    def quick_order(self, **kw):
        return request.render(TEMPLATE, self._qo_values())

    @http.route("/shop/quick-order", type="http", auth="user", website=True,
                methods=["POST"], csrf=True, sitemap=False)
    def quick_order_submit(self, lines="", **kw):
        """Read the list, add what can be added, show the rest line by line."""
        rows, errors, overflow = parse_order_text(lines, MAX_LINES)
        if overflow:
            # The cap is refused before a single product is looked up: it is
            # there to bound the work, so it cannot be applied halfway.
            error = message(
                request.env, TOO_MANY_LINES, max=MAX_LINES, count=overflow)
            return request.render(
                TEMPLATE, self._qo_values(lines=lines, error=error))
        added, refused = self._qo_cart()._qo_apply(rows, self._qo_pricelist())
        return request.render(TEMPLATE, self._qo_values(
            lines=lines,
            result=build_summary(request.env, added, errors + refused)))
