from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""  # Settings > API > JWT Secret

    # App base URL (for OAuth callbacks)
    app_base_url: str = "http://localhost:8099"

    # Shopify OAuth App (for multi-tenant installs)
    shopify_client_id: str = ""
    shopify_client_secret: str = ""

    # Amazon App credentials
    amazon_app_id: str = ""

    # Meta App
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_webhook_verify_token: str = "d2cflow-webhook"

    # Amazon SP-API
    amazon_refresh_token: str = ""
    amazon_client_id: str = ""
    amazon_client_secret: str = ""
    amazon_marketplace_id: str = "A21TJRUUN4KGV"  # India

    # Flipkart
    flipkart_client_id: str = ""
    flipkart_client_secret: str = ""

    # Meesho
    meesho_api_token: str = ""

    # Myntra
    myntra_supplier_id: str = ""
    myntra_api_key: str = ""

    # Ajio
    ajio_api_key: str = ""
    ajio_seller_id: str = ""

    # Nykaa
    nykaa_api_token: str = ""
    nykaa_seller_id: str = ""

    # Snapdeal
    snapdeal_api_token: str = ""
    snapdeal_seller_id: str = ""

    # FirstCry
    firstcry_api_token: str = ""
    firstcry_seller_code: str = ""

    # Zoho Books
    zoho_access_token: str = ""
    zoho_organization_id: str = ""

    # Tally (via TallyConnector bridge)
    tally_host: str = "http://localhost:9000"

    # Shopify
    shopify_store_url: str = ""  # e.g. yourstore.myshopify.com
    shopify_access_token: str = ""

    # Shiprocket
    shiprocket_email: str = ""
    shiprocket_password: str = ""

    # Razorpay
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # WhatsApp Cloud API (Meta)
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_business_account_id: str = ""

    # MoEngage Transactional Email
    moengage_app_id: str = ""
    moengage_api_key: str = ""
    moengage_api_host: str = "api-01.moengage.com"  # India: api-02, EU: api-03
    moengage_sender_email: str = ""
    moengage_sender_name: str = "D2C Flow"

    # App
    founder_whatsapp: str = ""  # e.g. 919876543210
    founder_email: str = ""
    low_stock_threshold: int = 10
    rtd_hours_threshold: int = 24   # flag as RTD after 24h if not dispatched
    cod_confirm_timeout_hours: int = 2

    class Config:
        env_file = [
            ".env",
            os.path.join(os.path.dirname(__file__), ".env"),
        ]
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
