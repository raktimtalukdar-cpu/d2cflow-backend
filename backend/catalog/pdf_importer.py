"""
PDF Catalog Importer — extracts product listings from a PDF catalog.

Strategy (in order):
  1. Table extraction — if PDF has proper tables with headers, map columns directly
  2. Pattern matching — scan raw text for price signals (₹ or INR) + nearby text
  3. Returns a list of extracted products for the merchant to review/confirm before saving
"""
import re
import io
import logging
from typing import IO

logger = logging.getLogger(__name__)

# Price patterns: ₹1,299 / Rs.1299 / INR 1299 / 1299/- / 1,299.00
PRICE_RE = re.compile(
    r"(?:₹|Rs\.?|INR|MRP:?|Price:?|Rate:?)\s*[\s]*([\d,]+(?:\.\d{1,2})?)"
    r"|(\d[\d,]+(?:\.\d{1,2})?)\s*(?:/[-–]|rupees?|INR)",
    re.IGNORECASE,
)
SKU_RE = re.compile(r"(?:SKU|Item\s*(?:No|Code|#)|Product\s*(?:No|Code|#))[\s:.-]*([A-Z0-9\-_]{3,20})", re.IGNORECASE)


def _clean_price(raw: str) -> float:
    try:
        return float(raw.replace(",", "").strip())
    except Exception:
        return 0.0


def _extract_from_tables(pdf_path_or_bytes) -> list[dict]:
    """Try to parse product tables. Returns [] if no usable tables found."""
    try:
        import pdfplumber
        products = []
        if isinstance(pdf_path_or_bytes, (bytes, bytearray)):
            f = io.BytesIO(pdf_path_or_bytes)
        else:
            f = pdf_path_or_bytes

        with pdfplumber.open(f) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    header_row = [str(h or "").strip().lower() for h in table[0]]
                    if not header_row or not any(h for h in header_row):
                        continue

                    # Map columns
                    col = {}
                    for i, h in enumerate(header_row):
                        if any(k in h for k in ("name", "product", "item", "description", "desc", "title")):
                            col.setdefault("name", i)
                        if any(k in h for k in ("price", "rate", "mrp", "cost", "amount", "₹")):
                            col.setdefault("price", i)
                        if any(k in h for k in ("sku", "code", "id", "item no", "product no", "hsn")):
                            col.setdefault("sku", i)
                        if any(k in h for k in ("qty", "stock", "quantity", "inventory")):
                            col.setdefault("stock", i)
                        if any(k in h for k in ("category", "cat", "type", "group")):
                            col.setdefault("category", i)
                        if any(k in h for k in ("mrp", "maximum", "max price")):
                            col.setdefault("mrp", i)

                    if "name" not in col and "price" not in col:
                        continue  # Not a product table

                    for row in table[1:]:
                        if not row or all(not c for c in row):
                            continue
                        def cell(key):
                            idx = col.get(key)
                            return str(row[idx] or "").strip() if idx is not None and idx < len(row) else ""

                        name = cell("name")
                        if not name or len(name) < 2:
                            continue

                        price_raw = cell("price")
                        price_m = PRICE_RE.search(price_raw) if price_raw else None
                        price_str = (price_m.group(1) or price_m.group(2)) if price_m else price_raw
                        price = _clean_price(price_str)

                        mrp_raw = cell("mrp")
                        mrp = _clean_price(PRICE_RE.search(mrp_raw).group(1) if PRICE_RE.search(mrp_raw) else mrp_raw) if mrp_raw else price

                        products.append({
                            "name": name[:120],
                            "sku": cell("sku") or "",
                            "price": price,
                            "mrp": mrp if mrp >= price else price,
                            "stock": int(cell("stock")) if cell("stock").isdigit() else 0,
                            "category": cell("category"),
                            "source": "pdf_table",
                        })

        return products
    except Exception as e:
        logger.debug(f"Table extraction failed: {e}")
        return []


def _extract_from_text(pdf_path_or_bytes) -> list[dict]:
    """Scan raw text for product name + price patterns."""
    try:
        import pdfplumber
        products = []
        if isinstance(pdf_path_or_bytes, (bytes, bytearray)):
            f = io.BytesIO(pdf_path_or_bytes)
        else:
            f = pdf_path_or_bytes

        with pdfplumber.open(f) as pdf:
            full_text = "\n".join(
                (page.extract_text() or "") for page in pdf.pages
            )

        # Split into blocks separated by double newlines or page breaks
        blocks = re.split(r"\n{2,}", full_text)

        for block in blocks:
            block = block.strip()
            if len(block) < 5:
                continue

            # Find price in block
            price_match = PRICE_RE.search(block)
            if not price_match:
                continue

            price = _clean_price(price_match.group(1) or price_match.group(2) or "0")
            if price <= 0:
                continue

            # First substantial line = product name
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            name = lines[0] if lines else block[:80]

            # Skip if name looks like a header/footer
            if len(name) < 3 or name.lower() in ("page", "total", "subtotal", "grand total", "amount"):
                continue

            # Description = remaining lines minus the price line
            desc_lines = [l for l in lines[1:] if not PRICE_RE.search(l)]
            description = " ".join(desc_lines[:3])[:200]

            # Try to find SKU
            sku_m = SKU_RE.search(block)
            sku = sku_m.group(1) if sku_m else ""

            products.append({
                "name": name[:120],
                "sku": sku,
                "price": price,
                "mrp": price,
                "stock": 0,
                "category": "",
                "description": description,
                "source": "pdf_text",
            })

        return products
    except Exception as e:
        logger.debug(f"Text extraction failed: {e}")
        return []


def parse_pdf_catalog(file_bytes: bytes) -> list[dict]:
    """
    Main entry point. Returns a list of product dicts for merchant review.
    Each product: {name, sku, price, mrp, stock, category, description, source}
    """
    # Try table extraction first (more structured)
    products = _extract_from_tables(file_bytes)

    if not products:
        # Fall back to text pattern matching
        products = _extract_from_text(file_bytes)

    # Deduplicate by name (case-insensitive)
    seen = set()
    unique = []
    for p in products:
        key = p["name"].lower().strip()
        if key not in seen and p.get("price", 0) > 0:
            seen.add(key)
            unique.append(p)

    return unique
