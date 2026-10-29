# -*- coding: utf-8 -*-
"""From a typed reference to the product the shop is willing to sell.

Two questions are answered here and they are deliberately separate: *which*
product the reference designates (and whether it designates one at all), then
whether that product may be sold on this website under this pricelist. A
reference that resolves to an unpublished product is not an unknown reference,
and the customer reads a different sentence for each.

The fixtures are class fixtures, so this series needs ``SavepointCase``: its
``TransactionCase`` builds the environment per test method and has no
``cls.env`` to build them with.
"""
from odoo.tests.common import SavepointCase

from odoo.addons.bs_quick_order.models.quick_order import (
    AMBIGUOUS_REFERENCE,
    NOT_FOR_SALE,
    NOT_IN_PRICELIST,
    NOT_PUBLISHED,
    UNKNOWN_REFERENCE,
)


class TestQuickOrderResolution(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super(TestQuickOrderResolution, cls).setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Quick order - general",
            "currency_id": cls.env.company.currency_id.id,
        })
        cls.wholesale = cls.env["product.pricelist"].create({
            "name": "Quick order - wholesale only",
            "currency_id": cls.env.company.currency_id.id,
        })

        cls.widget = cls._product("WIDGET-01", barcode="5901234123457")
        cls.box = cls._product("BOX-6")
        cls.hidden = cls._product("HIDDEN-1", is_published=False)
        cls.retired = cls._product("RETIRED-1")
        cls.retired.product_tmpl_id.active = False
        cls.service = cls._product("SERVICE-1", sale_ok=False)
        cls.wholesale_only = cls._product("WHOLE-1")
        # The only product the wholesale pricelist names.
        cls.wholesale.item_ids = [(0, 0, {
            "applied_on": "1_product",
            "product_tmpl_id": cls.wholesale_only.product_tmpl_id.id,
            "compute_price": "fixed",
            "fixed_price": 5.0,
        })]

    @classmethod
    def _product(cls, reference, **values):
        values.setdefault("name", reference)
        values.setdefault("type", "consu")
        values.setdefault("sale_ok", True)
        values.setdefault("is_published", True)
        values.setdefault("list_price", 10.0)
        values.setdefault("default_code", reference)
        return cls.env["product.template"].create(values).product_variant_id

    def _resolve(self, reference):
        return self.env["product.product"]._qo_resolve(reference)

    # ------------------------------------------------------------------
    # Which product
    # ------------------------------------------------------------------
    def test_a_product_is_found_by_its_internal_reference(self):
        product, code = self._resolve("WIDGET-01")
        self.assertEqual(product, self.widget)
        self.assertFalse(code)

    def test_the_reference_is_matched_case_insensitively(self):
        for written in ("widget-01", "Widget-01", "WIDGET-01"):
            product, code = self._resolve(written)
            self.assertEqual(product, self.widget, written)
            self.assertFalse(code)

    def test_a_barcode_is_used_when_no_reference_matches(self):
        product, code = self._resolve("5901234123457")
        self.assertEqual(product, self.widget)
        self.assertFalse(code)

    def test_the_internal_reference_wins_over_a_barcode(self):
        """Both point at a product; the reference is the one that decides."""
        self.box.barcode = "WIDGET-01"
        product, code = self._resolve("WIDGET-01")
        self.assertEqual(product, self.widget)
        self.assertFalse(code)

    def test_an_underscore_in_a_reference_is_not_a_wildcard(self):
        """``=ilike`` would otherwise match "SKUX001" against "SKU_001"."""
        underscored = self._product("SKU_001")
        self._product("SKUX001")
        product, code = self._resolve("sku_001")
        self.assertFalse(code)
        self.assertEqual(product, underscored)

    def test_an_unknown_reference_is_reported(self):
        product, code = self._resolve("NOTHING-LIKE-THIS")
        self.assertFalse(product)
        self.assertEqual(code, UNKNOWN_REFERENCE)

    def test_two_products_sharing_a_reference_are_ambiguous(self):
        self._product("DUP-1")
        self._product("DUP-1", name="Other duplicate")
        product, code = self._resolve("dup-1")
        self.assertFalse(product)
        self.assertEqual(code, AMBIGUOUS_REFERENCE)

    # ------------------------------------------------------------------
    # Whether it may be sold
    # ------------------------------------------------------------------
    def test_a_published_product_of_a_general_pricelist_is_sellable(self):
        self.assertFalse(self.widget._qo_rejection(self.pricelist))

    def test_an_unpublished_product_is_refused(self):
        self.assertEqual(self.hidden._qo_rejection(self.pricelist), NOT_PUBLISHED)

    def test_an_archived_product_is_refused(self):
        self.assertEqual(self.retired._qo_rejection(self.pricelist), NOT_FOR_SALE)

    def test_a_product_not_for_sale_is_refused(self):
        self.assertEqual(self.service._qo_rejection(self.pricelist), NOT_FOR_SALE)

    def test_a_product_left_out_of_the_pricelist_is_refused(self):
        """The wholesale list names one product; the others are not sold there."""
        self.assertFalse(
            self.wholesale_only._qo_rejection(self.wholesale),
            "the product the pricelist names must be sellable")
        self.assertEqual(
            self.widget._qo_rejection(self.wholesale), NOT_IN_PRICELIST)

    def test_a_pricelist_that_names_no_product_sells_the_catalogue(self):
        """Negative control: the ordinary shop is not restricted by this rule."""
        self.assertFalse(self.box._qo_rejection(self.pricelist))
        discounted = self.env["product.pricelist"].create({
            "name": "Quick order - one flat price",
            "currency_id": self.env.company.currency_id.id,
            "item_ids": [(0, 0, {
                "applied_on": "3_global",
                "compute_price": "fixed",
                "fixed_price": 10.0,
            })],
        })
        self.assertFalse(
            self.widget._qo_rejection(discounted),
            "a global rule prices the catalogue, it does not select from it")
