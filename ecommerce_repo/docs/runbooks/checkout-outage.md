# Checkout Outage Runbook

## Symptoms

- Payment returns HTTP 500 in checkout
- Coupon branch causes unhandled exception
- Spike in timeout and failed transactions

## Triage

1. Check payment gateway latency and error rate.
2. Inspect coupon validation branch and null/empty handling.
3. Review last deployment on checkout-service.

## Immediate Mitigation

- Disable problematic coupon campaign.
- Activate fallback payment route.
- Scale checkout workers if saturation is detected.

