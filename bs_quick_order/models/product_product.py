# -*- coding: utf-8 -*-
"""Turning a typed reference into the product the shop would sell.

The reference the customer knows is the internal reference first, the barcode
second: an invoice line quotes the first, the sticker on the shelf the second,
and both end up in the same box. Nothing here adds anything to a cart -- the
answer is a product and, when there is no usable one, the reason.
"""
from odoo import api, models

from .quick_order import (
    AMBIGUOUS_REFERENCE,
    NOT_FOR_SALE,
    NOT_IN_PRICELIST,
    NOT_PUBLISHED,
    UNKNOWN_REFERENCE,
)

#: Price rules that name specific products. A pricelist that carries at least
#: one of these is a list of what it sells, not a set of discounts on top of
#: the catalogue: see :meth:`_qo_in_pricelist`.
NAMING_RULES = ("0_product_variant", "1_product", "2_product_category")


def escape_like(value):
    """Neutralise the wildcards ``=ilike`` would otherwise honour.

    Internal references contain underscores all the time ("SKU_001"), and an
    underscore in a LIKE pattern matches any single character: without this,
    "sku_001" would also resolve "SKUX001" and the page would quietly add the
    wrong product.
    """
    return (value.replace("\\", "\\\\")
                 .replace("%", "\\%")
                 .replace("_", "\\_"))


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _qo_resolve(self, reference):
        """The product a reference designates, and how it failed.

        :return: ``(product, code)`` -- exactly one of the two is meaningful.
            An archived product still resolves, so the line can be told it is
            no longer sold instead of "no product matches".
        """
        reference = (reference or "").strip()
        if not reference:
            return self.browse(), UNKNOWN_REFERENCE
        products = self.sudo().with_context(active_test=False)
        by_reference = products.search(
            [("default_code", "=ilike", escape_like(reference))])
        if len(by_reference) > 1:
            return self.browse(), AMBIGUOUS_REFERENCE
        if by_reference:
            return by_reference, None
        by_barcode = products.search([("barcode", "=", reference)])
        if len(by_barcode) > 1:
            return self.browse(), AMBIGUOUS_REFERENCE
        if by_barcode:
            return by_barcode, None
        return self.browse(), UNKNOWN_REFERENCE

    def _qo_rejection(self, pricelist):
        """Why this product cannot be sold on the website, or ``None``."""
        self.ensure_one()
        template = self.product_tmpl_id
        if not self.active or not template.active or not template.sale_ok:
            return NOT_FOR_SALE
        if not template.website_published:
            return NOT_PUBLISHED
        if not self._qo_in_pricelist(pricelist):
            return NOT_IN_PRICELIST
        return None

    def _qo_in_pricelist(self, pricelist):
        """Whether the current pricelist sells this product.

        A pricelist that names products -- a product, a variant or a category
        rule -- sells those products, and a global rule adds the rest of the
        catalogue to them. A pricelist that names none is a general one and
        sells everything, which is the ordinary shop and the default state of
        a new database.

        The question is asked here rather than handed to the core's
        ``_is_add_to_cart_allowed`` because that method reads the request,
        and this answer is also needed from a test, a cron or a script.
        """
        self.ensure_one()
        if not pricelist:
            return True
        items = pricelist.sudo().item_ids
        if not items.filtered(lambda item: item.applied_on in NAMING_RULES):
            return True
        template = self.product_tmpl_id
        for item in items:
            if item.applied_on == "3_global":
                return True
            if item.applied_on == "1_product" and item.product_tmpl_id == template:
                return True
            if item.applied_on == "0_product_variant" and item.product_id == self:
                return True
            if item.applied_on == "2_product_category" and item.categ_id == template.categ_id:
                return True
        return False
