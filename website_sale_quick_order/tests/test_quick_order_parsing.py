# -*- coding: utf-8 -*-
"""What the textarea means, before a product is looked up.

Every assertion here is about the text the customer pasted: what a separator
is, which line number an answer will quote back, and what happens to a line
that cannot be read. The parser is deliberately free of the ORM, so these
tests need no product, no website and no cart.
"""
from odoo.tests.common import TransactionCase

from odoo.addons.website_sale_quick_order.models.quick_order import (
    INVALID_QUANTITY,
    MAX_LINES,
    MISSING_QUANTITY,
    NON_POSITIVE_QUANTITY,
    parse_order_text,
)


class TestQuickOrderParsing(TransactionCase):

    def _one_line(self, text):
        rows, errors, overflow = parse_order_text(text)
        self.assertEqual(overflow, 0)
        self.assertEqual(len(rows) + len(errors), 1, (rows, errors))
        return (rows or errors)[0]

    def _codes(self, text):
        _rows, errors, _overflow = parse_order_text(text)
        return [error["code"] for error in errors]

    # ------------------------------------------------------------------
    # Separators
    # ------------------------------------------------------------------
    def test_a_space_separates_the_reference_from_the_quantity(self):
        row = self._one_line("WIDGET-01 2")
        self.assertEqual(row["reference"], "WIDGET-01")
        self.assertEqual(row["quantity"], 2.0)

    def test_a_tab_separates_the_two(self):
        row = self._one_line("WIDGET-01\t2")
        self.assertEqual(row["reference"], "WIDGET-01")
        self.assertEqual(row["quantity"], 2.0)

    def test_a_semicolon_separates_the_two(self):
        row = self._one_line("WIDGET-01; 2")
        self.assertEqual(row["reference"], "WIDGET-01")
        self.assertEqual(row["quantity"], 2.0)

    def test_a_comma_separates_the_two(self):
        row = self._one_line("WIDGET-01,2")
        self.assertEqual(row["reference"], "WIDGET-01")
        self.assertEqual(row["quantity"], 2.0)

    def test_a_reference_may_contain_spaces(self):
        """The quantity is the last token, so the rest stays the reference."""
        row = self._one_line("WIDGET BLACK L 4")
        self.assertEqual(row["reference"], "WIDGET BLACK L")
        self.assertEqual(row["quantity"], 4.0)

    def test_a_decimal_quantity_is_kept(self):
        self.assertEqual(self._one_line("NUTS 0.25")["quantity"], 0.25)

    # ------------------------------------------------------------------
    # Lines and numbering
    # ------------------------------------------------------------------
    def test_blank_lines_are_ignored_and_do_not_shift_the_numbers(self):
        rows, errors, overflow = parse_order_text(
            "\n\nWIDGET-01 2\n\n\nBOX-6 3\n")
        self.assertEqual(overflow, 0)
        self.assertEqual(errors, [])
        self.assertEqual([row["line"] for row in rows], [3, 6])
        self.assertEqual([row["quantity"] for row in rows], [2.0, 3.0])

    def test_duplicates_are_summed_on_the_first_line(self):
        rows, errors, _overflow = parse_order_text(
            "WIDGET-01 2\nBOX-6 1\nWIDGET-01 3")
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 2, "the duplicate did not merge")
        self.assertEqual(rows[0]["reference"], "WIDGET-01")
        self.assertEqual(rows[0]["quantity"], 5.0)
        self.assertEqual(rows[0]["line"], 1)
        self.assertEqual(rows[0]["lines"], [1, 3])

    def test_the_merge_does_not_care_about_case(self):
        rows, _errors, _overflow = parse_order_text("widget-01 2\nWIDGET-01 3")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 5.0)

    # ------------------------------------------------------------------
    # Lines that cannot be read
    # ------------------------------------------------------------------
    def test_a_quantity_that_is_not_a_number_is_a_line_error(self):
        self.assertEqual(self._codes("WIDGET-01 two"), [INVALID_QUANTITY])
        self.assertEqual(self._codes("WIDGET-01 2x"), [INVALID_QUANTITY])

    def test_a_zero_quantity_is_a_line_error(self):
        self.assertEqual(self._codes("WIDGET-01 0"), [NON_POSITIVE_QUANTITY])
        self.assertEqual(self._codes("WIDGET-01 0.0"), [NON_POSITIVE_QUANTITY])

    def test_a_negative_quantity_is_a_line_error(self):
        self.assertEqual(self._codes("WIDGET-01 -2"), [NON_POSITIVE_QUANTITY])

    def test_a_line_without_a_quantity_is_a_line_error(self):
        self.assertEqual(self._codes("WIDGET-01"), [MISSING_QUANTITY])

    def test_an_error_keeps_the_line_number_it_was_written_on(self):
        _rows, errors, _overflow = parse_order_text("WIDGET-01 2\n\nNOPE x")
        self.assertEqual(errors[0]["line"], 3)
        self.assertEqual(errors[0]["quantity"], "x")

    # ------------------------------------------------------------------
    # The cap
    # ------------------------------------------------------------------
    def test_the_list_is_capped(self):
        text = "\n".join("SKU-%03d 1" % index for index in range(MAX_LINES + 1))
        rows, errors, overflow = parse_order_text(text)
        self.assertEqual(overflow, MAX_LINES + 1)
        self.assertEqual(rows, [], "an over-long list is refused as a whole")
        self.assertEqual(errors, [])

    def test_a_list_that_fits_the_cap_is_read(self):
        text = "\n".join("SKU-%03d 1" % index for index in range(MAX_LINES))
        rows, errors, overflow = parse_order_text(text)
        self.assertEqual(overflow, 0)
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), MAX_LINES)

    def test_blank_lines_do_not_count_towards_the_cap(self):
        text = "\n".join(
            "SKU-%03d 1\n" % index for index in range(MAX_LINES)
        ) + "\n\n\n"
        rows, _errors, overflow = parse_order_text(text)
        self.assertEqual(overflow, 0)
        self.assertEqual(len(rows), MAX_LINES)
