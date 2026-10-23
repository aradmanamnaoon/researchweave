from __future__ import annotations

from pathlib import Path

from researchweave.evidence.collections import CollectionService
from researchweave.evidence.library import LibraryService
from researchweave.evidence.storage import ProjectStore


def test_nested_collections_tags_filters_export_and_reopen(tmp_path: Path) -> None:
    root = tmp_path / "project"
    with ProjectStore.create(root, "Collections", "Organize references?", "exploratory") as store:
        imported = LibraryService(store).import_bibliography(
            b"@article{a,title={Alpha study},author={Doe, Ada},year={2024}}\n"
            b"@article{b,title={Beta study},author={Roe, Bea},year={2022}}",
            "bibtex",
        )
        ids = [record["id"] for record in imported["references"]]
        service = CollectionService(store)
        parent = service.create("Review")
        child = service.create("Included", parent["collection_id"])
        service.add_members(child["collection_id"], ids)
        service.tag([ids[0]], ["Priority"])
        filtered = service.search(collection_id=child["collection_id"], year_from=2023)
        assert filtered[0]["id"] == ids[0]
        assert service.search(tag="priority")[0]["id"] == ids[0]
        assert "Alpha study" in service.export_csv(child["collection_id"])
        tree = service.tree()
        assert tree[0]["id"] == parent["collection_id"]
        assert tree[0]["children"][0]["id"] == child["collection_id"]
    with ProjectStore(root) as reopened:
        service = CollectionService(reopened)
        assert len(service.search(collection_id=child["collection_id"])) == 2
        assert reopened.audit()["ok"]


def test_collection_batch_remove_is_reversible_by_readding(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Collections", "Question", "exploratory"
    ) as store:
        imported = LibraryService(store).import_bibliography(
            b"@article{a,title={Alpha},author={Doe, Ada},year={2024}}", "bibtex"
        )
        reference_id = imported["references"][0]["id"]
        service = CollectionService(store)
        collection_id = service.create("Set")["collection_id"]
        service.add_members(collection_id, [reference_id])
        service.remove_members(collection_id, [reference_id])
        assert service.search(collection_id=collection_id) == []
        service.add_members(collection_id, [reference_id])
        assert service.search(collection_id=collection_id)[0]["id"] == reference_id


def test_collection_export_exposes_alias_provenance(tmp_path: Path) -> None:
    with ProjectStore.create(
        tmp_path / "project", "Collections", "Question", "exploratory"
    ) as store:
        library = LibraryService(store)
        imported = library.import_bibliography(
            b"@article{a,title={Same},author={Doe, Ada},year={2024}}\n"
            b"@article{b,title={Same},author={Doe, Ada},year={2024}}", "bibtex")
        canonical, alias = [record["id"] for record in imported["references"]]
        library.merge_references(canonical, alias, "Reviewer confirmed duplicate")
        service = CollectionService(store)
        collection = service.create("Aliases")["collection_id"]
        service.add_members(collection, [alias])
        record = service.search(collection_id=collection)[0]
        assert record["id"] == alias
        assert record["canonical_id"] == canonical
        assert record["is_alias"] is True
        exported = service.export_csv(collection)
        assert canonical in exported and alias in exported
