from api.app.ticket_watchers import map_external_status_to_internal


def test_map_external_status_to_internal_resolved_variants() -> None:
    assert map_external_status_to_internal("jira", "Done") == "resolved"
    assert map_external_status_to_internal("jira", "Resolved") == "resolved"
    assert map_external_status_to_internal("jira", "Closed") == "resolved"


def test_map_external_status_to_internal_open_variants() -> None:
    assert map_external_status_to_internal("jira", "To Do") == "open"
    assert map_external_status_to_internal("jira", "In Progress") == "processing"
