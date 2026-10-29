# -*- coding: utf-8 -*-
"""Putting the readable lines in the cart, one at a time.

The core add path is used as it is. Everything the shop enforces around a
single add -- the stock rule of ``website_sale_stock``, a zero price, the
options a combo needs -- is enforced there, and calling it means this page
cannot disagree with the product page about what may be bought. The only
thing added here is the loop, and the fact that a refusal on one line is
collected instead of aborting the submission: a typo on line three must not
cost the customer lines one and two.
"""
from odoo import models
from odoo.exceptions import UserError

from .quick_order import SHOP_REFUSED


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _qo_apply(self, rows, pricelist):
        """Add every usable row to this cart.

        :param list rows: the parsed rows, see
            :func:`odoo.addons.website_sale_quick_order.models.quick_order.parse_order_text`
        :param pricelist: the pricelist the cart is being priced with
        :return: ``(added, errors)`` -- the rows that reached the cart and the
            rows that did not, each carrying the ``code`` that says why
        """
        self.ensure_one()
        Product = self.env["product.product"]
        added, errors = [], []
        for row in rows:
            product, code = Product._qo_resolve(row["reference"])
            if not code:
                code = product._qo_rejection(pricelist)
            if code:
                errors.append(dict(row, code=code))
                continue
            try:
                values = self._qo_add(product, row["quantity"])
            except UserError as error:
                errors.append(dict(row, code=SHOP_REFUSED, detail=str(error)))
                continue
            added.append(dict(row, product=product,
                              warning=values.get("warning") or ""))
        return added, errors

    def _qo_add(self, product, quantity):
        """The cart add of this series, unchanged.

        19.0 moved the cart to ``_cart_add``, which takes the quantity to add;
        before that the same job is ``_cart_update`` with ``add_qty``.
        """
        return self._cart_add(product.id, quantity)
