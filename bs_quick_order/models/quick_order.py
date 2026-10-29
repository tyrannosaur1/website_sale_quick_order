# -*- coding: utf-8 -*-
"""Reading the pasted list.

The textarea is the whole user interface of this module, so the rules of the
text live here, away from the ORM: one product per line, a reference and a
quantity, and a line that cannot be read is reported with the number the
customer sees in their own text.

Nothing here touches the database. The parser returns *codes*, not sentences,
so the same result can be asserted on in a test and translated for the page.

Separators are a tab, a space, a semicolon or a comma. A reference may itself
contain spaces ("WIDGET BLACK L"), so the quantity is the last token on the
line and everything before it is the reference: the customer's habit of
writing "reference quantity" decides the split, not ours.
"""
import math
import re

#: Lines a single submission may carry. Ten products in a paste is an order;
#: ten thousand is a textarea nobody reads, resolved one query at a time.
MAX_LINES = 100

#: One line: a reference, a separator, a quantity. The reference is lazy and
#: the quantity is the last run of non-space characters, so the separator this
#: matches is the *last* one on the line.
LINE_RE = re.compile(r"^(?P<reference>.+?)[\s;,]+(?P<quantity>\S+)$")

#: Why a line was refused. Codes rather than sentences: the page translates
#: them, the tests assert on them, and neither has to parse the other's text.
MISSING_QUANTITY = "missing_quantity"
INVALID_QUANTITY = "invalid_quantity"
NON_POSITIVE_QUANTITY = "non_positive_quantity"
UNKNOWN_REFERENCE = "unknown_reference"
AMBIGUOUS_REFERENCE = "ambiguous_reference"
NOT_PUBLISHED = "not_published"
NOT_FOR_SALE = "not_for_sale"
NOT_IN_PRICELIST = "not_in_pricelist"
SHOP_REFUSED = "shop_refused"
TOO_MANY_LINES = "too_many_lines"


def translate(env, text):
    """Translate *text* with whichever accessor this series provides.

    ``env._`` exists from 18.0 on and is the preferred door; the module-level
    ``_`` is the one 16.0 and 17.0 have.
    """
    translator = getattr(env, "_", None)
    if callable(translator):
        return translator(text)
    from odoo import _
    return _(text)


def user_error_text(error):
    """The sentence of a ``UserError``, without the tuple 10.0 keeps.

    ``UserError`` is an ``except_orm`` carrying ``(message, '')`` here, and
    ``str()`` on it prints the tuple -- not a sentence a customer should
    read under their line.
    """
    args = getattr(error, "args", ())
    return args[0] if args else str(error)


def format_quantity(quantity):
    """A quantity as a customer should read it: 5, 0.25, 1.5 -- no `.0`."""
    value = float(quantity or 0.0)
    if value == int(value):
        return str(int(value))
    return ("%.6f" % value).rstrip("0").rstrip(".")


def parse_quantity(text):
    """The number on a line, or ``None`` when there is not one.

    ``float()`` accepts "nan" and "inf"; neither is an order, and both would
    reach the cart as a quantity nothing in the shop can compare.
    """
    try:
        quantity = float(text)
    except (TypeError, ValueError):
        return None
    if math.isinf(quantity) or math.isnan(quantity):
        return None
    return quantity


def parse_order_text(text, max_lines=MAX_LINES):
    """Read the textarea into the rows the cart will be asked to add.

    :param str text: what the customer pasted or typed
    :param int max_lines: the cap; 0 means no cap
    :return: ``(rows, errors, overflow)``

        ``rows`` holds one entry per *distinct* reference -- duplicates are
        summed into the line the reference first appeared on -- in the order
        the customer wrote them. ``errors`` holds the lines that could not be
        read at all. ``overflow`` is the number of lines typed when the list
        is over the cap, and 0 otherwise: a list that long is refused as a
        whole, because the cap protects the server rather than the order.

    A row is ``{"line", "lines", "reference", "quantity"}``: ``line`` is the
    first physical line the reference appeared on and is what the answer
    quotes back, ``lines`` every line that was merged into it.
    """
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    typed = [(number, line) for number, line in enumerate(lines, 1) if line.strip()]
    if max_lines and len(typed) > max_lines:
        return [], [], len(typed)

    rows, merged, errors = [], {}, []
    for number, line in typed:
        raw = line.strip()
        match = LINE_RE.match(raw)
        if not match:
            errors.append({
                "line": number, "reference": raw, "quantity": "",
                "code": MISSING_QUANTITY})
            continue
        reference = match.group("reference").strip()
        quantity_text = match.group("quantity").strip()
        quantity = parse_quantity(quantity_text)
        if quantity is None:
            errors.append({
                "line": number, "reference": reference, "quantity": quantity_text,
                "code": INVALID_QUANTITY})
            continue
        if quantity <= 0:
            errors.append({
                "line": number, "reference": reference, "quantity": quantity_text,
                "code": NON_POSITIVE_QUANTITY})
            continue
        # A reference is read case-insensitively, so the merge key is too:
        # "abc-1 2" and "ABC-1 3" are one product ordered five times.
        key = reference.lower()
        if key in merged:
            merged[key]["quantity"] += quantity
            merged[key]["lines"].append(number)
            continue
        row = {"line": number, "lines": [number],
               "reference": reference, "quantity": quantity}
        merged[key] = row
        rows.append(row)
    return rows, errors, 0


def message(env, code, **values):
    """The sentence the customer reads for one refused line."""
    if code == MISSING_QUANTITY:
        return translate(
            env, u"No quantity on this line: write the reference, a space, "
                 "then the quantity.")
    if code == INVALID_QUANTITY:
        return translate(env, u"%(quantity)s is not a number.") % values
    if code == NON_POSITIVE_QUANTITY:
        return translate(env, u"The quantity must be greater than zero.")
    if code == UNKNOWN_REFERENCE:
        return translate(env, u"No product matches this reference.")
    if code == AMBIGUOUS_REFERENCE:
        return translate(
            env, u"Several products share this reference: add this one from its "
                 "product page.")
    if code == NOT_PUBLISHED:
        return translate(env, u"This product is not published on the website.")
    if code == NOT_FOR_SALE:
        return translate(env, u"This product is not for sale on the website.")
    if code == NOT_IN_PRICELIST:
        return translate(env, u"This product is not part of the current pricelist.")
    if code == SHOP_REFUSED:
        # The shop's own sentence, kept as it is: the page must not explain a
        # stock or configuration rule differently from the product page.
        return values.get("detail") or translate(
            env, u"The shop refused this line.")
    if code == TOO_MANY_LINES:
        return translate(
            env, u"The list is limited to %(max)s lines; %(count)s were pasted."
        ) % values
    return translate(env, u"This line could not be added.")


def build_summary(env, added, errors):
    """The two lists the page prints, already spelled for the customer."""
    for entry in added:
        entry["quantity_label"] = format_quantity(entry["quantity"])
    for entry in errors:
        values = dict(entry)
        values.pop("code", None)
        entry["message"] = message(env, entry["code"], **values)
    return {
        "added": added,
        "errors": errors,
        "added_label": (
            translate(env, u"1 line was added to your cart.")
            if len(added) == 1 else
            translate(env, u"%(count)s lines were added to your cart.") % {
                "count": len(added)}
        ) if added else "",
        "error_label": (
            translate(env, u"1 line could not be added:")
            if len(errors) == 1 else
            translate(env, u"%(count)s lines could not be added:") % {
                "count": len(errors)}
        ) if errors else "",
        "nothing_label": translate(env, u"Nothing was added to your cart."),
    }
