"""Generated capability schemas are real runtime-enforced public contracts."""

from researchweave.evidence import build_evidence_facade


def test_all_registered_operations_advertise_consistent_typed_contracts(tmp_path):
    facade = build_evidence_facade(tmp_path)
    manifest = facade.capability_manifest()
    assert len(manifest) >= 100
    assert len({item["operation"] for item in manifest}) == len(manifest)
    for capability in manifest:
        declared = capability["arguments_schema"]
        assert declared["type"] == "object"
        assert set(capability["required_arguments"]) == set(declared["required"])
        for field in declared["required"]:
            assert field in declared["properties"]
            assert declared["properties"][field]["type"] in {
                "string", "integer", "array", "object", "boolean"}
        response = capability["result_schema"]
        assert {"request_id", "status", "data", "error", "impact"} <= (
            set(response["required"]))
        assert capability["required_permission"] == capability["effect"]
        assert isinstance(capability["risks"], list)
        assert isinstance(capability["constraints"], list)
        assert capability["readiness"] in {"implemented", "requires-explicit-network"}
        assert capability["reversibility"] in {
            "no-side-effects", "no-local-side-effects", "operation-specific-audited"}
        if capability["effect"] == "external-network":
            assert not capability["offline"]
            assert "provider_metadata_may_be_inaccurate" in capability["risks"]
            assert capability["readiness"] == "requires-explicit-network"
            assert capability["transmitted_data"]
            assert capability["network_hosts"]
        else:
            assert capability["transmitted_data"] == []
    encrypted = next(item for item in manifest if item["operation"] ==
                     "project.archive_encrypted")
    assert encrypted["arguments_schema"]["properties"]["password"]["writeOnly"]


def test_type_and_size_failures_precede_filesystem_side_effects(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    bad = facade.execute("project.create", {"title": ["wrong"],
                                            "question": "Valid question",
                                            "design": "exploratory"}, {})
    assert bad["status"] == "failed" and bad["error"]["code"] == "INVALID_INPUT"
    assert not list(tmp_path.iterdir())
    invalid_privacy = facade.execute("project.create", {"title": "Title",
                                                    "question": "Question", "design": "exploratory",
                                                    "privacy": "global"}, {})
    assert invalid_privacy["error"]["code"] == "INVALID_INPUT"
    assert not list(tmp_path.iterdir())
    bad_preview = facade.preview("project.create", {"title": "Project",
        "question": "Question", "design": {"unsafe": "type"}}, {})
    assert bad_preview["error"]["code"] == "INVALID_INPUT"
    assert not list(tmp_path.iterdir())
    huge_b64 = facade.execute("migration.zotero_preview", {
        "data_base64": "A" * (45 * 1024 * 1024 + 1)}, {})
    assert huge_b64["error"]["code"] == "RESOURCE_LIMIT"
    assert not list(tmp_path.iterdir())


def test_invalid_array_item_rejected_without_touching_project(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    created = facade.execute("project.create", {"title": "Contract",
        "question": "What is the source?", "design": "exploratory"}, {})
    pid = created["data"]["project_id"]
    bad = facade.execute("library.reference_tag", {"project_id": pid,
        "reference_ids": [42], "tags": ["reviewed"]}, {})
    assert bad["error"]["code"] == "INVALID_INPUT"
    assert facade.execute("project.open", {"project_id": pid}, {})[
        "data"]["revision"] == 0


def test_missing_required_and_numeric_ranges_are_runtime_enforced(tmp_path):
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    missing = facade.execute("project.create", {
        "question": "What is missing?", "design": "exploratory"}, {})
    assert missing["status"] == "failed"
    assert missing["error"]["code"] == "INVALID_INPUT"
    assert not list(tmp_path.iterdir())

    created = facade.execute("project.create", {
        "title": "Ranges", "question": "Are bounds enforced?",
        "design": "exploratory"}, {})
    pid = created["data"]["project_id"]
    too_small = facade.execute("project.timeline", {
        "project_id": pid, "limit": 0}, {})
    assert too_small["error"]["code"] == "INVALID_INPUT"
    too_large = facade.execute("project.timeline", {
        "project_id": pid, "limit": 1001}, {})
    assert too_large["error"]["code"] == "RESOURCE_LIMIT"


def test_result_schema_matches_public_success_and_failure_statuses(tmp_path):
    facade = build_evidence_facade(tmp_path)
    schema = facade.capability_manifest()[0]["result_schema"]
    assert schema["properties"]["status"]["enum"] == ["ok", "failed"]
    success = facade.health()
    assert success["status"] == "ok"
    failure = facade.execute("not.registered", {}, {})
    assert failure["status"] == "failed"
