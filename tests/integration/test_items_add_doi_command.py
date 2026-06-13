"""tests/integration/test_items_add_doi_command.py"""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from zotero_cli.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tmp_profile(monkeypatch, tmp_path):
    cfg = tmp_path / "zotero-cli" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from zotero_cli.adapters.config_store import write_toml

    write_toml(
        cfg,
        {"default": {"api_key": "k", "library_id": "1", "library_type": "user"}},
    )
    return cfg


SAMPLE_MESSAGE: dict[str, Any] = {
    "type": "journal-article",
    "DOI": "10.1038/s41586-020-2649-2",
    "title": ["Array programming with NumPy"],
    "author": [{"given": "Charles R.", "family": "Harris"}],
    "container-title": ["Nature"],
    "published-print": {"date-parts": [[2020, 9, 17]]},
    "volume": "585",
    "issue": "7825",
    "page": "357-362",
    "publisher": "Springer Science and Business Media LLC",
    "ISSN": ["0028-0836"],
    "URL": "http://dx.doi.org/10.1038/s41586-020-2649-2",
}


class TestAddDoiDryRun:
    def test_dry_run_json_output(self, mocker, runner, tmp_profile, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.doi_metadata.crossref.CrossrefProvider.fetch",
            return_value=SAMPLE_MESSAGE,
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item_template",
            return_value={
                "itemType": "",
                "title": "",
                "creators": [],
                "date": "",
                "DOI": "",
                "url": "",
                "abstractNote": "",
                "tags": [],
                "collections": [],
                "publicationTitle": "",
                "volume": "",
                "issue": "",
                "pages": "",
                "ISSN": "",
                "publisher": "",
            },
        )
        result = runner.invoke(
            app,
            ["--json", "items", "add-doi", "10.1038/s41586-020-2649-2", "--dry-run"],
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["ok"] is True
        assert env["data"]["dry_run"] is True
        assert len(env["data"]["would_create"]) == 1
        item = env["data"]["would_create"][0]
        assert item["title"] == "Array programming with NumPy"
        assert item["itemType"] == "journalArticle"
        assert env["meta"]["dry_run"] is True
        assert env["meta"]["source"] == "crossref"
        assert env["meta"]["normalized_doi"] == "10.1038/s41586-020-2649-2"

    def test_dry_run_does_not_create(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.doi_metadata.crossref.CrossrefProvider.fetch",
            return_value=SAMPLE_MESSAGE,
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item_template",
            return_value={
                "itemType": "",
                "title": "",
                "creators": [],
                "date": "",
                "DOI": "",
                "url": "",
                "abstractNote": "",
                "tags": [],
                "collections": [],
                "publicationTitle": "",
                "volume": "",
                "issue": "",
                "pages": "",
                "ISSN": "",
                "publisher": "",
            },
        )
        mock_create = mocker.patch("zotero_cli.adapters.zotero_api.ZoteroAPI.create_items")
        runner.invoke(
            app,
            ["items", "add-doi", "10.1038/s41586-020-2649-2", "--dry-run"],
        )
        mock_create.assert_not_called()


class TestAddDoiCreate:
    def test_create_default_output(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.doi_metadata.crossref.CrossrefProvider.fetch",
            return_value=SAMPLE_MESSAGE,
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item_template",
            return_value={
                "itemType": "",
                "title": "",
                "creators": [],
                "date": "",
                "DOI": "",
                "url": "",
                "abstractNote": "",
                "tags": [],
                "collections": [],
                "publicationTitle": "",
                "volume": "",
                "issue": "",
                "pages": "",
                "ISSN": "",
                "publisher": "",
            },
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.create_items",
            return_value={
                "successful": [{"index": 0, "key": "DOIKEY", "version": 1}],
                "unchanged": [],
                "failed": [],
            },
        )
        result = runner.invoke(
            app,
            ["items", "add-doi", "10.1038/s41586-020-2649-2"],
        )
        assert result.exit_code == 0
        assert "Created" in result.stdout
        assert "DOIKEY" in result.stdout

    def test_create_with_tags(self, mocker, runner, tmp_profile, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.doi_metadata.crossref.CrossrefProvider.fetch",
            return_value=SAMPLE_MESSAGE,
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item_template",
            return_value={
                "itemType": "",
                "title": "",
                "creators": [],
                "date": "",
                "DOI": "",
                "url": "",
                "abstractNote": "",
                "tags": [],
                "collections": [],
                "publicationTitle": "",
                "volume": "",
                "issue": "",
                "pages": "",
                "ISSN": "",
                "publisher": "",
            },
        )
        mock_create = mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.create_items",
            return_value={
                "successful": [{"index": 0, "key": "TAGKEY", "version": 1}],
                "unchanged": [],
                "failed": [],
            },
        )
        result = runner.invoke(
            app,
            ["--json", "items", "add-doi", "10.1038/s41586-020-2649-2", "--tags", "ai,paper"],
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["ok"] is True
        payload = mock_create.call_args[0][0][0]
        assert payload["tags"] == [{"tag": "ai"}, {"tag": "paper"}]

    def test_create_with_collection(
        self, mocker, runner, tmp_profile, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        mocker.patch(
            "zotero_cli.adapters.doi_metadata.crossref.CrossrefProvider.fetch",
            return_value=SAMPLE_MESSAGE,
        )
        mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.item_template",
            return_value={
                "itemType": "",
                "title": "",
                "creators": [],
                "date": "",
                "DOI": "",
                "url": "",
                "abstractNote": "",
                "tags": [],
                "collections": [],
                "publicationTitle": "",
                "volume": "",
                "issue": "",
                "pages": "",
                "ISSN": "",
                "publisher": "",
            },
        )
        mock_create = mocker.patch(
            "zotero_cli.adapters.zotero_api.ZoteroAPI.create_items",
            return_value={
                "successful": [{"index": 0, "key": "COLLKEY", "version": 1}],
                "unchanged": [],
                "failed": [],
            },
        )
        result = runner.invoke(
            app,
            ["--json", "items", "add-doi", "10.1038/s41586-020-2649-2", "--collection", "MYCOLL"],
        )
        assert result.exit_code == 0
        env = json.loads(result.stdout)
        assert env["ok"] is True
        payload = mock_create.call_args[0][0][0]
        assert payload["collections"] == ["MYCOLL"]


class TestAddDoiErrors:
    def test_invalid_doi(self, runner, tmp_profile, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = runner.invoke(app, ["--json", "items", "add-doi", "not-a-doi"])
        assert result.exit_code == 1
        env = json.loads(result.stdout)
        assert env["ok"] is False
        assert env["error"]["code"] == "INVALID_FIELD"
