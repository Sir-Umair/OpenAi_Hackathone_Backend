from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import GeneratedFile
from app.services import ConversionError, migration_recommendations, selected_source_files, source_files, write_conversion


def test_conversion_targets_are_available() -> None:
    response = TestClient(app).get("/api/v1/conversion-targets")

    assert response.status_code == 200
    assert "Next.js + FastAPI" in response.json()["targets"]
    assert response.json()["custom_target_supported"] is True


def test_legacy_php_and_jquery_receive_recommendations(tmp_path: Path) -> None:
    (tmp_path / "legacy.php").write_text("<?php echo 'hello';", encoding="utf-8")
    (tmp_path / "ui.js").write_text("$('#menu').hide();", encoding="utf-8")

    recommendations = migration_recommendations(source_files(tmp_path))

    assert {recommendation.current_technology for recommendation in recommendations} == {"PHP", "jQuery"}


def test_conversion_source_and_output_stay_separate(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('hello')", encoding="utf-8")

    with pytest.raises(ConversionError, match="escapes"):
        selected_source_files(project, ["../outside.py"])

    output = tmp_path / "converted"
    write_conversion(output, [GeneratedFile(path="app/main.py", content="print('converted')")])

    assert (output / "app" / "main.py").read_text(encoding="utf-8") == "print('converted')"
    assert (project / "main.py").read_text(encoding="utf-8") == "print('hello')"