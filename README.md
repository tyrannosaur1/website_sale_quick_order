# Quick Order by Reference

Paste a list of product references and quantities; the shop adds every line it can and names the lines it cannot.

Odoo 10.0 – 20.0. One branch per series, the branch name is the series.

## What it does

- A page at `/shop/quick-order`, linked from the shop header, for signed-in customers.
- One product per line: `reference quantity`, separated by a space, a tab, a semicolon or a comma. Blank lines are ignored.
- A reference is resolved against the internal reference first, then the barcode; an unknown or ambiguous one is reported with its line number.
- Duplicate references are summed into one line of the cart, case-insensitively.
- Products that cannot be sold on the site — unpublished, not for sale, or outside the current pricelist — are line errors.
- A line the shop itself refuses (the stock rule, a zero price) is a line error too; the page adds through the shop's own path, so nothing is forced in.
- The valid lines always reach the cart, whatever happened to the others, and the answer lists what was added and what failed.
- A submission is capped at 100 lines and the cap is refused whole.

## Install

1. Copy the module into your addons path.
2. Update the app list, install **Quick Order by Reference**.
3. Sign in to the website as a customer and open **Quick order** in the shop header.

## Notes

- The pricelist question is answered by the pricelist's own rules: a pricelist that names products sells those products, and a global rule adds the rest of the catalogue. A pricelist that names nothing is a general one and sells everything.
- The form posts with CSRF on, like every other form of the site.

## License

OPL-1. See `LICENSE`.

## Support

Open an issue on this repository.
