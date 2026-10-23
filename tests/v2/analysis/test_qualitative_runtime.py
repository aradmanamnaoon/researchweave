import pytest

from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.qualitative import (
    Code,
    CodingProject,
    Transcript,
    cohen_kappa,
)
from researchweave.analysis.runtime import RuntimeAuthorizer, run_script


def test_unicode_spans_overlap_and_export_roundtrip():
    project = CodingProject()
    project.add_transcript(Transcript("story", "درود 🌍 hello", "case-1"))
    project.add_code(Code("theme", "Theme"))
    project.add_code(Code("nested", "Nested", parent="theme"))
    one = project.annotate("story", 5, 8, "theme", "coder-a", "unit-1")
    two = project.annotate("story", 6, 8, "nested", "coder-b", "unit-1")
    assert project.verify(one) and project.verify(two)
    copy = CodingProject.from_json(project.to_json())
    assert copy.annotations == project.annotations
    with pytest.raises(AnalysisError, match="CONFLICT"):
        project.annotate("story", 5, 8, "theme", "coder-a", "unit-1")


def test_kappa_manual_oracle_and_unit_mismatch():
    result = cohen_kappa(
        {"a": "1", "b": "1", "c": "0", "d": "0"}, {"a": "1", "b": "0", "c": "0", "d": "0"}
    )
    assert result["observed_agreement"] == pytest.approx(0.75)
    assert result["expected_agreement"] == pytest.approx(0.5)
    assert result["kappa"] == pytest.approx(0.5)
    with pytest.raises(AnalysisError, match="SCHEMA_MISMATCH"):
        cohen_kappa({"a": "1"}, {"b": "1"})
    with pytest.raises(AnalysisError, match="undefined"):
        cohen_kappa({"a": "1"}, {"a": "1"})


def test_script_consent_output_failure_and_timeout():
    authorizer = RuntimeAuthorizer()
    with pytest.raises(AnalysisError, match="NEEDS_APPROVAL"):
        run_script("print(2)", authorizer=authorizer)
    source = "print(2 + 3)"
    result = run_script(source, authorizer=authorizer, approval=authorizer.issue(source))
    assert result["stdout"].strip() == "5"
    assert result["exit_code"] == 0
    failure_source = "raise ValueError('bad input')"
    failure = run_script(
        failure_source,
        authorizer=authorizer,
        approval=authorizer.issue(failure_source),
    )
    assert failure["status"] == "failed"
    assert "ValueError" in failure["stderr"]
    changed = authorizer.issue("print(1)")
    with pytest.raises(AnalysisError, match="changed after approval"):
        run_script("print(2)", authorizer=authorizer, approval=changed)
    timeout_source = "import time; time.sleep(5)"
    with pytest.raises(AnalysisError, match="CANCELLED"):
        run_script(
            timeout_source,
            authorizer=authorizer,
            approval=authorizer.issue(timeout_source, timeout_seconds=1),
            timeout_seconds=1,
        )


def test_script_artifact_hash_and_one_time_approval():
    authorizer = RuntimeAuthorizer()
    source = "from pathlib import Path; Path('result.txt').write_text('ok'); print('done')"
    approval = authorizer.issue(source)
    result = run_script(source, authorizer=authorizer, approval=approval)
    assert result["artifacts"][0]["path"] == "result.txt"
    assert len(result["artifacts"][0]["sha256"]) == 64
    assert result["runner_version"]
    with pytest.raises(AnalysisError, match="already used"):
        run_script(source, authorizer=authorizer, approval=approval)
