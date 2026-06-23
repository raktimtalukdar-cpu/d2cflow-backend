"""
Integration setup guides — structured, step-by-step instructions per channel.
Returns direct links, field explanations, and format examples so the frontend
can render a guided wizard instead of a blank credential form.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/integrations/guide", tags=["integrations"])

# ------------------------------------------------------------------ #
# Guide definitions
# ------------------------------------------------------------------ #

GUIDES: dict[str, dict] = {

    "shopify": {
        "channel": "shopify",
        "title": "Connect Shopify",
        "logo": "🛒",
        "estimated_minutes": 2,
        "summary": "Connect your Shopify store using an Admin API token. Takes about 2 minutes.",
        "steps": [
            {
                "n": 1,
                "title": "Open your Shopify admin",
                "instruction": "Log in to your Shopify store.",
                "url_template": "https://{shop_domain}/admin",
                "url_label": "Open Shopify Admin",
            },
            {
                "n": 2,
                "title": "Go to Apps → Develop apps",
                "instruction": "In your Shopify admin, click Settings (bottom-left) → Apps and sales channels → Develop apps. If you don't see this, enable developer preview first.",
                "url_template": "https://{shop_domain}/admin/settings/apps/development",
                "url_label": "Open App Development",
            },
            {
                "n": 3,
                "title": "Create a new app",
                "instruction": "Click 'Create an app', give it any name (e.g. 'd2cflow'), then click Configure Admin API scopes. Enable: read_orders, write_orders, read_products, write_products, read_inventory, write_inventory.",
                "url_template": None,
                "url_label": None,
            },
            {
                "n": 4,
                "title": "Install the app and copy the token",
                "instruction": "Click 'Install app', then reveal and copy the Admin API access token. It starts with 'shpat_'. You'll only see this once — paste it below.",
                "url_template": None,
                "url_label": None,
            },
        ],
        "fields": [
            {
                "key": "shop_domain",
                "label": "Shop domain",
                "type": "text",
                "placeholder": "your-store.myshopify.com",
                "format": "xxxx.myshopify.com",
                "example": "bluetea.myshopify.com",
                "where": "This is your Shopify store's URL",
                "required": True,
            },
            {
                "key": "access_token",
                "label": "Admin API access token",
                "type": "password",
                "placeholder": "shpat_xxxxxxxxxxxxxxxxxxxx",
                "format": "starts with shpat_",
                "example": "shpat_abc123...",
                "where": "Shopify Admin → Settings → Apps → Develop apps → Your app → API credentials",
                "required": True,
            },
        ],
        "common_errors": [
            "Token starts with shpak_ not shpat_ — that's a public app token, not admin API. Create a custom app instead.",
            "Store not found — check the domain is yourstore.myshopify.com not yourstore.com",
            "Invalid token — you may need to reinstall the app and copy the token again",
        ],
    },

    "amazon": {
        "channel": "amazon",
        "title": "Connect Amazon Seller Central",
        "logo": "📦",
        "estimated_minutes": 5,
        "summary": "Connect Amazon via SP-API. You need your Seller ID and MWS Auth Token.",
        "steps": [
            {
                "n": 1,
                "title": "Find your Seller ID",
                "instruction": "Log in to Seller Central India. Click your account name (top right) → Account Info. Your Seller ID (Merchant Token) is listed there. It starts with the letter A.",
                "url_template": "https://sellercentral.amazon.in/sw/AccountInfo/MerchantToken/step/MerchantToken",
                "url_label": "Open Account Info",
            },
            {
                "n": 2,
                "title": "Authorize the app",
                "instruction": "Click 'Connect Amazon' below. You'll be redirected to Seller Central to approve d2cflow. After approving, you'll be sent back automatically.",
                "url_template": None,
                "url_label": None,
            },
        ],
        "fields": [
            {
                "key": "seller_id",
                "label": "Seller ID (Merchant Token)",
                "type": "text",
                "placeholder": "A2EUQ1WTGCTBG2",
                "format": "Starts with A, all uppercase letters and numbers",
                "example": "A2EUQ1WTGCTBG2",
                "where": "Seller Central → Account Info → Merchant Token",
                "required": True,
            },
            {
                "key": "mws_token",
                "label": "MWS Auth Token",
                "type": "password",
                "placeholder": "amzn.mws.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                "format": "amzn.mws. followed by a UUID",
                "example": "amzn.mws.4ea38b7b-f563-7709-4bae-87aeaEXAMPLE",
                "where": "Seller Central → Developer Tools → MWS Developer Access → Auth Token",
                "required": True,
            },
        ],
        "common_errors": [
            "Seller ID should start with 'A' — don't use your store name or email",
            "MWS token is different from your password — it's in Developer Tools",
        ],
    },

    "flipkart": {
        "channel": "flipkart",
        "title": "Connect Flipkart Seller Hub",
        "logo": "🛍️",
        "estimated_minutes": 3,
        "summary": "Connect using your Flipkart API App ID and App Secret from Seller Hub.",
        "steps": [
            {
                "n": 1,
                "title": "Open Seller Hub API settings",
                "instruction": "Log in to Flipkart Seller Hub. Go to Settings → API Settings. If you don't see this, your account may need API access enabled — contact Flipkart seller support.",
                "url_template": "https://seller.flipkart.com/index.html#dashboard/settings/api-settings",
                "url_label": "Open API Settings",
            },
            {
                "n": 2,
                "title": "Create an app",
                "instruction": "Click 'Add new app', name it 'd2cflow', and set the redirect URL to your d2cflow domain. Copy the App ID and App Secret shown.",
                "url_template": None,
                "url_label": None,
            },
        ],
        "fields": [
            {
                "key": "app_id",
                "label": "App ID",
                "type": "text",
                "placeholder": "FK_APP_XXXXXXXX",
                "format": "Starts with FK_APP_ or similar",
                "example": "FK_APP_abc123",
                "where": "Flipkart Seller Hub → Settings → API Settings → Your App",
                "required": True,
            },
            {
                "key": "app_secret",
                "label": "App Secret",
                "type": "password",
                "placeholder": "••••••••••••••••",
                "format": "Long alphanumeric string",
                "example": "abc123def456...",
                "where": "Flipkart Seller Hub → Settings → API Settings → Your App",
                "required": True,
            },
        ],
        "common_errors": [
            "API access must be enabled on your Flipkart account first — contact Flipkart seller support if you don't see API Settings",
        ],
    },

    "meesho": {
        "channel": "meesho",
        "title": "Connect Meesho Supplier",
        "logo": "🪡",
        "estimated_minutes": 2,
        "summary": "One field only — your Meesho API token from Supplier Hub.",
        "steps": [
            {
                "n": 1,
                "title": "Open Supplier Hub settings",
                "instruction": "Log in to Meesho Supplier Hub. Click your profile (top right) → Settings → API Integration. If you don't see this section, contact Meesho support to enable API access.",
                "url_template": "https://supplier.meesho.com/settings/api-integration",
                "url_label": "Open API Settings",
            },
            {
                "n": 2,
                "title": "Copy your API token",
                "instruction": "Your API token is shown on the API Integration page. Copy and paste it below.",
                "url_template": None,
                "url_label": None,
            },
        ],
        "fields": [
            {
                "key": "api_token",
                "label": "API Token",
                "type": "password",
                "placeholder": "meesho_api_xxxxxxxxxxxx",
                "format": "Long alphanumeric token",
                "example": "meesho_api_abc123...",
                "where": "Meesho Supplier Hub → Settings → API Integration",
                "required": True,
            },
        ],
        "common_errors": [
            "API access is not available to all suppliers by default — contact Meesho support at supplier-support@meesho.com",
        ],
    },

    "myntra": {
        "channel": "myntra",
        "title": "Connect Myntra Partner",
        "logo": "👗",
        "estimated_minutes": 3,
        "summary": "Connect using your Myntra Supplier ID and API Key from Partner Portal.",
        "steps": [
            {
                "n": 1,
                "title": "Open Myntra Partner Portal",
                "instruction": "Log in to Myntra Partner Portal. Go to Settings → API Integration. Your Supplier ID is shown at the top of the page.",
                "url_template": "https://myntrapartners.com",
                "url_label": "Open Partner Portal",
            },
            {
                "n": 2,
                "title": "Generate an API key",
                "instruction": "In Settings → API Integration, click Generate API Key. Copy both the Supplier ID and the API Key.",
                "url_template": None,
                "url_label": None,
            },
        ],
        "fields": [
            {
                "key": "supplier_id",
                "label": "Supplier ID",
                "type": "text",
                "placeholder": "MYN_SUPPLIER_XXXXX",
                "format": "Your Myntra supplier identifier",
                "example": "MYN_SUPPLIER_12345",
                "where": "Myntra Partner Portal → top of Settings page",
                "required": True,
            },
            {
                "key": "api_key",
                "label": "API Key",
                "type": "password",
                "placeholder": "••••••••••••••••",
                "format": "Long alphanumeric string",
                "example": "abc123...",
                "where": "Myntra Partner Portal → Settings → API Integration → Generate API Key",
                "required": True,
            },
        ],
        "common_errors": [
            "API access must be requested from Myntra — not all seller accounts have it by default",
        ],
    },

    "shiprocket": {
        "channel": "shiprocket",
        "title": "Connect Shiprocket",
        "logo": "🚀",
        "estimated_minutes": 1,
        "summary": "Just your Shiprocket login email and password. That's it.",
        "steps": [
            {
                "n": 1,
                "title": "Use your Shiprocket credentials",
                "instruction": "Enter the same email and password you use to log in to app.shiprocket.in. d2cflow will use these to authenticate with Shiprocket's API.",
                "url_template": "https://app.shiprocket.in",
                "url_label": "Open Shiprocket",
            },
        ],
        "fields": [
            {
                "key": "email",
                "label": "Shiprocket email",
                "type": "email",
                "placeholder": "you@yourbrand.in",
                "format": "Your Shiprocket login email",
                "example": "ops@bluetea.in",
                "where": "Your Shiprocket account login email",
                "required": True,
            },
            {
                "key": "password",
                "label": "Shiprocket password",
                "type": "password",
                "placeholder": "••••••••",
                "format": "Your Shiprocket account password",
                "example": "",
                "where": "Your Shiprocket account login password",
                "required": True,
            },
        ],
        "common_errors": [
            "Wrong password — reset it at app.shiprocket.in/reset-password",
            "Account not active — your Shiprocket account needs to be active with a valid plan",
        ],
    },

    "razorpay": {
        "channel": "razorpay",
        "title": "Connect Razorpay",
        "logo": "💳",
        "estimated_minutes": 2,
        "summary": "Connect your Razorpay account so payment links show your brand. Customers pay directly to your account.",
        "steps": [
            {
                "n": 1,
                "title": "Open Razorpay API Keys",
                "instruction": "Log in to your Razorpay dashboard. Go to Settings → API Keys. If you haven't generated keys yet, click Generate Test Key Pair first, then switch to Live when ready.",
                "url_template": "https://dashboard.razorpay.com/app/keys",
                "url_label": "Open Razorpay API Keys",
            },
            {
                "n": 2,
                "title": "Copy Key ID and Key Secret",
                "instruction": "Copy the Key ID (starts with rzp_test_ or rzp_live_) and the Key Secret. The secret is only shown once — if you've lost it, regenerate both keys.",
                "url_template": None,
                "url_label": None,
            },
            {
                "n": 3,
                "title": "Add webhook (optional but recommended)",
                "instruction": "In Razorpay Dashboard → Webhooks, add a new webhook pointing to your d2cflow URL: https://yourdomain.com/api/payments/webhook. Enable events: payment.captured and payment_link.paid. This lets orders auto-confirm and shipments auto-create on payment.",
                "url_template": "https://dashboard.razorpay.com/app/webhooks",
                "url_label": "Open Webhooks",
            },
        ],
        "fields": [
            {
                "key": "key_id",
                "label": "Key ID",
                "type": "text",
                "placeholder": "rzp_test_xxxxxxxxxxxx or rzp_live_xxxxxxxxxxxx",
                "format": "rzp_test_ (test mode) or rzp_live_ (production)",
                "example": "rzp_test_abc123XYZ",
                "where": "Razorpay Dashboard → Settings → API Keys",
                "required": True,
            },
            {
                "key": "key_secret",
                "label": "Key Secret",
                "type": "password",
                "placeholder": "••••••••••••••••••••",
                "format": "Alphanumeric, shown only once on generation",
                "example": "",
                "where": "Razorpay Dashboard → Settings → API Keys (shown when generated)",
                "required": True,
            },
        ],
        "common_errors": [
            "Key ID and Secret must match — both test or both live, not mixed",
            "Key Secret is only shown once — if you lost it, go to Razorpay Dashboard and regenerate both keys",
            "Using test keys in production won't capture real payments",
        ],
    },

    "nykaa": {
        "channel": "nykaa",
        "title": "Connect Nykaa Seller Hub",
        "logo": "💄",
        "estimated_minutes": 3,
        "summary": "Connect using your Nykaa API Token and Seller ID.",
        "steps": [
            {
                "n": 1,
                "title": "Open Nykaa Seller Hub",
                "instruction": "Log in to Nykaa Seller Hub. Go to Settings → API Integration. Your Seller ID is visible at the top.",
                "url_template": "https://seller.nykaa.com",
                "url_label": "Open Seller Hub",
            },
            {
                "n": 2,
                "title": "Generate API token",
                "instruction": "Under API Integration, click Generate Token. Copy both your Seller ID and the generated API token.",
                "url_template": None,
                "url_label": None,
            },
        ],
        "fields": [
            {
                "key": "seller_id",
                "label": "Seller ID",
                "type": "text",
                "placeholder": "NYK_XXXXX",
                "format": "Your Nykaa seller identifier",
                "example": "NYK_12345",
                "where": "Nykaa Seller Hub → Settings → API Integration",
                "required": True,
            },
            {
                "key": "api_token",
                "label": "API Token",
                "type": "password",
                "placeholder": "nyk_api_xxxxxxxxxxxx",
                "format": "Token starting with nyk_api_ or similar",
                "example": "nyk_api_abc123...",
                "where": "Nykaa Seller Hub → Settings → API Integration → Generate Token",
                "required": True,
            },
        ],
        "common_errors": [
            "API access needs to be enabled for your account — contact Nykaa seller support if you don't see API Integration",
        ],
    },

    "zoho": {
        "channel": "zoho",
        "title": "Connect Zoho Books",
        "logo": "📊",
        "estimated_minutes": 5,
        "summary": "Connect Zoho Books to auto-generate invoices for every order.",
        "steps": [
            {
                "n": 1,
                "title": "Get your Organization ID",
                "instruction": "Log in to Zoho Books. Go to Settings → Organization Profile. Your Organization ID is shown there.",
                "url_template": "https://books.zoho.in/app#/settings/organization",
                "url_label": "Open Organization Settings",
            },
            {
                "n": 2,
                "title": "Generate an Access Token",
                "instruction": "Go to Zoho API Console (api-console.zoho.in). Create a Self Client, add scope: ZohoBooks.fullaccess.all. Generate a code and exchange it for a token. Paste the access token below.",
                "url_template": "https://api-console.zoho.in",
                "url_label": "Open Zoho API Console",
            },
        ],
        "fields": [
            {
                "key": "organization_id",
                "label": "Organization ID",
                "type": "text",
                "placeholder": "XXXXXXXXXX",
                "format": "10-digit number",
                "example": "1234567890",
                "where": "Zoho Books → Settings → Organization Profile",
                "required": True,
            },
            {
                "key": "access_token",
                "label": "Access Token",
                "type": "password",
                "placeholder": "1000.xxxxxxxxxx.xxxxxxxxxx",
                "format": "Zoho OAuth token starting with 1000.",
                "example": "1000.abc123...",
                "where": "Zoho API Console → Self Client → Generate token",
                "required": True,
            },
        ],
        "common_errors": [
            "Tokens expire after 1 hour — use a refresh token flow for production (contact us to set this up)",
            "Organization ID is numeric — don't use the company name",
        ],
    },
}


# ------------------------------------------------------------------ #
# Endpoints
# ------------------------------------------------------------------ #

@router.get("")
def list_guides():
    """List all available integration guides (summary only)."""
    return [
        {
            "channel": g["channel"],
            "title": g["title"],
            "logo": g["logo"],
            "estimated_minutes": g["estimated_minutes"],
            "summary": g["summary"],
            "field_count": len(g["fields"]),
        }
        for g in GUIDES.values()
    ]


@router.get("/{channel}")
def get_guide(channel: str):
    """Full step-by-step setup guide for a specific channel."""
    guide = GUIDES.get(channel.lower())
    if not guide:
        raise HTTPException(
            status_code=404,
            detail=f"No guide available for '{channel}'. Available: {', '.join(GUIDES.keys())}",
        )
    return guide
