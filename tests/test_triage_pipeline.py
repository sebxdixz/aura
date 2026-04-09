from __future__ import annotations

import unittest

from api.app.models import AttachmentRecord, TriageOutput
from api.app.triage_pipeline import (
    build_rag_query,
    extract_entities,
    infer_service,
    merge_extracted_entities,
    normalize_incident_input,
    route_incident,
    score_severity,
    summarize_retrieved_context,
    validate_triage_output,
)


class TriagePipelineTests(unittest.TestCase):
    def test_payment_incident_scores_high_and_routes_to_payments(self) -> None:
        attachment = AttachmentRecord(
            attachment_type="log",
            attachment_filename="checkout.log",
            attachment_mime_type="text/plain",
            attachment_size_bytes=120,
            attachment_storage_path="/tmp/checkout.log",
            attachment_text_extracted="payment failed http 500 checkout gateway timeout all users",
            attachment_summary="Log shows payment failed and gateway timeout during checkout.",
            evidence_from_attachment=["HTTP 500", "payment failed", "gateway timeout"],
            attachment_signals={
                "suspected_service_from_attachment": "payment-service",
                "error_codes_found": ["500", "timeout"],
                "severity_hints": ["high"],
                "keywords_found": ["payment failed", "checkout"],
            },
            attachment_used=True,
            extraction_method="decode_text",
        )
        normalized = normalize_incident_input(
            incident_id="inc-1",
            tenant_id="tenant-demo",
            reporter_email="merchant@example.com",
            description="All users cannot pay in checkout. Payment failed with HTTP 500 in production.",
            attachment=attachment,
            trace_id="trace-1",
        )
        entities = extract_entities(normalized)
        rag_query = build_rag_query(normalized, entities)
        context = summarize_retrieved_context(
            rag_query,
            [
                {"file_path": "services/payment/gateway.py", "content": "payment gateway timeout and retry budget"},
                {"file_path": "docs/payment-runbook.md", "content": "payment incident runbook"},
            ],
        )
        primary_service, secondary = infer_service(
            normalized=normalized,
            entities=entities,
            retrieved_context=context,
        )
        severity = score_severity(
            normalized=normalized,
            entities=entities,
            retrieved_context=context,
            primary_service=primary_service,
        )
        routing = route_incident(
            primary_service=primary_service,
            secondary_candidates=secondary,
            entities=entities,
            normalized=normalized,
            retrieved_context=context,
        )

        self.assertEqual(entities.incident_type, "payment_failure")
        self.assertEqual(primary_service, "payment-service")
        self.assertIn(severity.label, {"high", "critical"})
        self.assertEqual(routing.target_team, "Payments")
        self.assertGreaterEqual(routing.routing_confidence, 0.6)

    def test_validate_triage_output_backfills_routing_defaults(self) -> None:
        triage = TriageOutput(
            severity="medium",
            affected_service="auth-service",
            technical_summary="Auth issue",
            root_cause_analysis="Token refresh path may be failing.",
            proposed_fix="Add explicit handling for expired sessions.",
            proposed_cli_command="pytest tests/test_auth.py -k token",
            llm_mode="mock",
            target_team="",
            routing_reasoning="",
            confidence=1.3,
            routing_confidence=1.4,
        )

        validated = validate_triage_output(triage)

        self.assertEqual(validated.target_team, "Identity/Auth")
        self.assertTrue(validated.routing_reasoning)
        self.assertEqual(validated.confidence, 1.0)
        self.assertEqual(validated.routing_confidence, 1.0)

    def test_llm_entity_merge_is_schema_guarded(self) -> None:
        normalized = normalize_incident_input(
            incident_id="inc-2",
            tenant_id="tenant-demo",
            reporter_email="user@example.com",
            description="Users hit login and get 401 in production.",
            attachment=None,
            trace_id="trace-2",
        )
        base = extract_entities(normalized)

        merged, changed = merge_extracted_entities(
            base,
            {
                "incident_type": "authentication_failure",
                "affected_surface": "login",
                "observed_error": "auth_failure",
                "user_scope": "many_users",
                "possible_environment": "production",
                "keywords": ["login", "auth", "401"],
                "security_risk_signals": ["unauthorized"],
                "business_impact_signals": ["cannot login"],
                "workaround_present": False,
                "unexpected_field": "ignored",
            },
        )

        self.assertTrue(changed)
        self.assertEqual(merged.incident_type, "authentication_failure")
        self.assertEqual(merged.affected_surface, "login")
        self.assertEqual(merged.observed_error, "auth_failure")
        self.assertEqual(merged.user_scope, "many_users")
        self.assertEqual(merged.possible_environment, "production")


if __name__ == "__main__":
    unittest.main()
