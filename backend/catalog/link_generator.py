"""
Server-side message template builder — mirrors CRMPage.jsx DRAFT_TEMPLATES
so bulk broadcasts produce the same messages as the dashboard composer.
"""

TEMPLATES = {
    "offer": lambda p, name: (
        f"Hi {name}! 👋\n\n"
        f"We have an exciting offer for you!\n\n"
        f"🛍️ *{p['name']}*"
        + (f"\n~~₹{p['mrp']}~~ → *₹{p['price']}*" if p.get('mrp') and p.get('price') and p['mrp'] > p['price']
           else f"\n*₹{p['price']}*" if p.get('price') else "")
        + (f"\n{p['description']}\n" if p.get('description') else "\n")
        + "\nOrder now and get it delivered to your doorstep! 🚀\n\n"
        "Reply *YES* to place your order."
    ),
    "restock": lambda p, name: (
        f"Hi {name}! 😊\n\n"
        f"Great news — *{p['name']}* is back in stock!\n"
        + (f"\nPrice: *₹{p['price']}*" if p.get('price') else "")
        + "\n\nReply *YES* to reserve yours right away. 📦"
    ),
    "new_launch": lambda p, name: (
        f"Hi {name}! 🎉\n\n"
        f"Exciting news! We just launched *{p['name']}*!\n"
        + (f"\n{p['description']}\n" if p.get('description') else "")
        + (f"\nIntroductory price: *₹{p['price']}*\n" if p.get('price') else "")
        + "\nBe among the first to try it — reply *BUY* to order now! 🛒"
    ),
    "followup": lambda p, name: (
        f"Hi {name}! 👋\n\n"
        f"Just checking in — were you interested in *{p['name']}*?"
        + (f" It's available at *₹{p['price']}*." if p.get('price') else "")
        + "\n\nLet me know if you have any questions — happy to help! 😊"
    ),
}


def generate_product_message(product: dict, template: str = "offer", contact_name: str = "{name}") -> str:
    """
    Generate a WhatsApp message for a product.

    product dict keys used: name, price, mrp, description, images[]
    contact_name: substituted for {name} placeholder — pass the actual name for bulk sends.
    """
    p = {
        "name": product.get("name", ""),
        "price": product.get("selling_price") or product.get("price"),
        "mrp": product.get("mrp"),
        "description": (product.get("description") or "").replace("<[^>]+>", "").strip()[:200],
    }

    fn = TEMPLATES.get(template, TEMPLATES["offer"])
    return fn(p, contact_name)


def product_to_dict(product_row: dict) -> dict:
    """Normalize a DB products row into the shape generate_product_message expects."""
    skus = product_row.get("skus") or []
    first_sku = skus[0] if skus else {}
    return {
        "name": product_row.get("name", ""),
        "selling_price": first_sku.get("selling_price") or product_row.get("selling_price"),
        "mrp": first_sku.get("mrp") or product_row.get("mrp"),
        "description": product_row.get("description", ""),
        "images": product_row.get("images", []),
    }
