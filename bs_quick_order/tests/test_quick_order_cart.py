# -*- coding: utf-8 -*-
"""What actually lands in the cart when the list is submitted.

The rule this file defends is the one sentence of the specification that is
easy to get wrong: a typo on one line must not cost the customer the other
lines. The mixed submission below is therefore the central test, and the
totals are read from the cart rather than from the values the add returned --
a line that "was added" to a cart whose total disagrees is not added.
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.bs_quick_order.models.quick_order import (
    NOT_PUBLISHED,
    SHOP_REFUSED,
    UNKNOWN_REFERENCE,
    parse_order_text,
)


class TestQuickOrderCart(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        # A pricelist of our own: 19.0 dropped ``website.pricelist_id``, and a
        # pricelist that names products would restrict the fixture itself.
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Quick order - public",
            "currency_id": cls.env.company.currency_id.id,
        })
        cls.partner = cls.env["res.partner"].create({"name": "Bulk Buyer"})
        cls.widget = cls._product("WIDGET-01", 10.0)
        cls.box = cls._product("BOX-6", 4.0)

    @classmethod
    def _product(cls, reference, price, **values):
        values.setdefault("name", reference)
        values.setdefault("type", "consu")
        values.setdefault("sale_ok", True)
        values.setdefault("is_published", True)
        values.setdefault("default_code", reference)
        values.setdefault("taxes_id", [(6, 0, [])])
        return cls.env["product.template"].create(
            dict(values, list_price=price)).product_variant_id

    def _order(self):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id,
            "pricelist_id": self.pricelist.id,
        })

    def _submit(self, order, text, pricelist=None):
        rows, errors, overflow = parse_order_text(text)
        self.assertEqual(overflow, 0)
        added, refused = order._qo_apply(rows, pricelist or self.pricelist)
        return added, errors + refused

    def _quantity(self, order, product):
        lines = order.order_line.filtered(lambda line: line.product_id == product)
        self.assertEqual(len(lines), 1, "expected exactly one line for %s" % product.name)
        return lines.product_uom_qty

    # ------------------------------------------------------------------
    # The mixed submission
    # ------------------------------------------------------------------
    def test_two_good_lines_and_one_typo(self):
        order = self._order()
        # the typo sits in the middle on purpose: an implementation that
        # stops at the first refusal must lose the line that follows it.
        added, errors = self._submit(
            order, "WIDGET-01 2\nNOPE 1\nBOX-6 3")
        self.assertEqual(len(added), 2, "the two readable lines must be added")
        self.assertEqual(len(errors), 1, "the typo must be reported once")
        self.assertEqual(errors[0]["line"], 2)
        self.assertEqual(errors[0]["code"], UNKNOWN_REFERENCE)
        self.assertEqual(len(order.order_line), 2)
        self.assertEqual(self._quantity(order, self.widget), 2.0)
        self.assertEqual(self._quantity(order, self.box), 3.0)
        # 2 * 10 + 3 * 4: the total follows the quantities, not the text
        self.assertEqual(order.amount_untaxed, 32.0)

    def test_a_submission_of_typos_only_adds_nothing(self):
        """Negative control: nothing is written when nothing resolves."""
        order = self._order()
        added, errors = self._submit(order, "NOPE 1\nALSO-NOPE 2")
        self.assertEqual(added, [])
        self.assertEqual([error["line"] for error in errors], [1, 2])
        self.assertFalse(order.order_line)
        self.assertEqual(order.amount_untaxed, 0.0)

    def test_a_reference_written_twice_is_one_cart_line(self):
        order = self._order()
        added, errors = self._submit(order, "WIDGET-01 2\nbox-6 1\nwidget-01 3")
        self.assertEqual(errors, [])
        self.assertEqual(len(added), 2)
        self.assertEqual(len(order.order_line), 2)
        self.assertEqual(self._quantity(order, self.widget), 5.0)
        self.assertEqual(order.amount_untaxed, 54.0)

    def test_a_second_submission_adds_to_the_line_already_there(self):
        order = self._order()
        self._submit(order, "WIDGET-01 2")
        self._submit(order, "WIDGET-01 3")
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(self._quantity(order, self.widget), 5.0)

    def test_a_line_that_cannot_be_sold_never_reaches_the_cart(self):
        hidden = self._product("HIDDEN-1", 10.0, is_published=False)
        order = self._order()
        added, errors = self._submit(order, "HIDDEN-1 2\nWIDGET-01 1")
        self.assertEqual(len(added), 1)
        self.assertEqual(errors[0]["code"], NOT_PUBLISHED)
        self.assertFalse(
            order.order_line.filtered(lambda line: line.product_id == hidden))

    def test_the_cart_is_priced_with_the_pricelist_the_page_read(self):
        """A negotiated price must be the price of the line, not the list one."""
        wholesale = self.env["product.pricelist"].create({
            "name": "Quick order - negotiated",
            "currency_id": self.env.company.currency_id.id,
            "item_ids": [(0, 0, {
                "applied_on": "1_product",
                "product_tmpl_id": self.widget.product_tmpl_id.id,
                "compute_price": "fixed",
                "fixed_price": 7.0,
            })],
        })
        order = self._order()
        order.pricelist_id = wholesale
        added, errors = self._submit(order, "WIDGET-01 2", pricelist=wholesale)
        self.assertEqual(errors, [])
        self.assertEqual(len(added), 1)
        self.assertEqual(order.order_line.price_unit, 7.0)
        self.assertEqual(order.amount_untaxed, 14.0)

    # ------------------------------------------------------------------
    # The shop's own refusals
    # ------------------------------------------------------------------
    def test_the_line_is_added_through_the_shops_own_path(self):
        """Stock, price and configuration rules live in that method.

        The page must not write ``sale.order.line`` records itself: the one
        promise that cannot be seen in a cart total is that the rules the
        product page obeys are obeyed here too, and the way to keep it is to
        call the method that enforces them.
        """
        order = self._order()
        rows, _errors, _overflow = parse_order_text("WIDGET-01 1")
        method = "_cart_add" if hasattr(order, "_cart_add") else "_cart_update"
        with patch.object(type(order), method, autospec=True,
                          side_effect=UserError("Not enough stock.")) as add:
            added, errors = order._qo_apply(rows, self.pricelist)
        self.assertTrue(add.called, "the line was written without the shop")
        self.assertEqual(added, [])
        self.assertEqual(errors[0]["code"], SHOP_REFUSED)

    def test_a_refusal_from_the_shop_is_a_line_error(self):
        """The stock rule and the other core checks must not abort the order."""
        order = self._order()
        rows, _errors, _overflow = parse_order_text("WIDGET-01 1\nBOX-6 2")
        with patch.object(type(order), "_qo_add",
                          side_effect=UserError("Not enough stock.")):
            added, errors = order._qo_apply(rows, self.pricelist)
        self.assertEqual(added, [])
        self.assertEqual([error["code"] for error in errors], [SHOP_REFUSED] * 2)
        self.assertEqual(errors[0]["detail"], "Not enough stock.")
        self.assertFalse(order.order_line)
