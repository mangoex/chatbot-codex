from __future__ import annotations

SKILL_TEMPLATES = {
    "support_ticket": {
        "name": "Soporte de Tickets (Zendesk / CRM)",
        "description": "Configura un webhook automático que se dispara cuando la conversación requiere crear un ticket de soporte utilizando <code>[[CREATE_TICKET: {...}]]</code>.",
        "skill_type": "webhook",
        "config": {
            "mode": "post_marker_payload",
            "url": "https://api.zendesk.com/v2/tickets",
            "marker": "[[CREATE_TICKET: {\"subject\": \"...\", \"description\": \"...\"}]]",
            "headers": {"Content-Type": "application/json"}
        }
    },
    "shopify_search": {
        "name": "Buscador de Productos Shopify",
        "description": "Configura una llamada API externa para buscar productos en tu tienda Shopify usando <code>[[SEARCH_PRODUCTS: {\"query\": \"...\"}]]</code>.",
        "skill_type": "external_api",
        "config": {
            "mode": "marker_based",
            "endpoint": "https://{shop}.myshopify.com/admin/api/2023-04/products.json",
            "marker": "[[SEARCH_PRODUCTS: {\"query\": \"...\"}]]",
            "allowed_methods": ["GET"]
        }
    },
    "stripe_payments": {
        "name": "Cobros con Stripe",
        "description": "Configura un webhook para generar enlaces de pago Stripe dinámicamente con <code>[[GENERATE_PAYMENT: {\"amount\": 147}]]</code>.",
        "skill_type": "webhook",
        "config": {
            "mode": "post_marker_payload",
            "url": "https://api.stripe.com/v1/payment_links",
            "marker": "[[GENERATE_PAYMENT: {\"amount\": 147, \"currency\": \"usd\"}]]"
        }
    }
}
