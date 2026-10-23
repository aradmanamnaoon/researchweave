from pathlib import Path

import pytest

from researchweave.analysis.datasets import import_csv, set_variable
from researchweave.analysis.errors import AnalysisError
from researchweave.analysis.mixed_methods import (
    case_code_matrix,
    code_cooccurrence,
    joint_display,
)
from researchweave.analysis.qualitative import Code, CodingProject, Transcript


@pytest.fixture
def linked(tmp_path: Path):
    path = tmp_path / "cases.csv"
    path.write_text("case,score\n1,1\n2,2\n3,3\n4,4\n5,5\n6,6\n", encoding="utf-8")
    data = import_csv(path)
    codes = CodingProject()
    codes.add_code(Code("theme", "Theme"))
    codes.add_code(Code("context", "Context"))
    for i in range(1, 7):
        source_id = f"transcript-{i}"
        codes.add_transcript(Transcript(source_id, "hello 🌍 world", str(i)))
        if i <= 3:
            codes.annotate(source_id, 0, 7, "theme", "researcher", f"unit-{i}")
            codes.annotate(source_id, 5, 10, "context", "researcher", f"unit-{i}")
    return data, codes


def test_joint_display_trace_and_disclosure_minimum(linked):
    data, project = linked
    view = joint_display(data, project, case_column="case", measure_column="score", code_id="theme")
    assert view["groups"]["coded"]["mean"] == pytest.approx(2)
    assert view["groups"]["not_coded"]["mean"] == pytest.approx(5)
    assert view["excerpts"] == []
    assert case_code_matrix(project)["n_annotations"] == 6
    overlaps = code_cooccurrence(project)
    assert overlaps["pairs"][0]["n_overlapping_pairs"] == 3
    with pytest.raises(AnalysisError, match="PERMISSION_DENIED"):
        joint_display(
            data,
            project,
            case_column="case",
            measure_column="score",
            code_id="theme",
            allow_quotes=True,
        )


def test_mapping_integrity_and_private_columns(linked):
    data, project = linked
    private = set_variable(data, "score", private=True)
    with pytest.raises(AnalysisError, match="PERMISSION_DENIED"):
        joint_display(private, project, case_column="case", measure_column="score", code_id="theme")
    with pytest.raises(AnalysisError, match="PRIVACY_THRESHOLD"):
        joint_display(
            data,
            project,
            case_column="case",
            measure_column="score",
            code_id="theme",
            min_reporting_cases=4,
        )
    project.transcripts["transcript-6"] = Transcript("transcript-6", "changed", "unknown")
    with pytest.raises(AnalysisError, match="SCHEMA_MISMATCH"):
        joint_display(data, project, case_column="case", measure_column="score", code_id="theme")
