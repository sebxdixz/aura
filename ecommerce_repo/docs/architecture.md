# E-commerce Service Architecture

Core services:

- `checkout-service`: handles cart validation, coupon application, payment submission.
- `catalog-service`: serves product listing and cache management.
- `auth-service`: login/session/token lifecycle.

Incident-sensitive integrations:

- Payment gateway API
- Inventory provider
- Identity provider

