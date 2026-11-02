import json
from pathlib import Path
from typing import Any

import pytest

from tranpro.paths import AppPaths
from tranpro.publication.auth import GoogleAuthError, install_client_credentials
from tranpro.publication.google_docs import GoogleDocsPublisher
from tranpro.publication.models import DocumentBlock, DocumentContent


class Call:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result

    def execute(self) -> dict[str, Any]:
        return self.result


class Documents:
    def __init__(self) -> None:
        self.batches: list[dict[str, Any]] = []

    def create(self, **_: Any) -> Call:
        return Call({"documentId": "doc-1"})

    def batchUpdate(self, **kwargs: Any) -> Call:  # noqa: N802
        self.batches.append(kwargs)
        return Call({})

    def get(self, **_: Any) -> Call:
        return Call({"body": {"content": [{"endIndex": 25}]}})


class DocsService:
    def __init__(self) -> None:
        self.resource = Documents()

    def documents(self) -> Documents:
        return self.resource


class Files:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def get(self, **_: Any) -> Call:
        return Call({"parents": ["root"]})

    def update(self, **kwargs: Any) -> Call:
        self.updates.append(kwargs)
        return Call({})


class DriveService:
    def __init__(self) -> None:
        self.resource = Files()

    def files(self) -> Files:
        return self.resource


def test_google_adapter_creates_styles_and_moves_document() -> None:
    docs = DocsService()
    drive = DriveService()
    publisher = GoogleDocsPublisher(docs_service=docs, drive_service=drive)
    content = DocumentContent("Title", (DocumentBlock("Title", "TITLE"),))

    remote = publisher.create(content, folder_id="folder-1")

    assert remote.id == "doc-1"
    assert docs.resource.batches[0]["documentId"] == "doc-1"
    assert drive.resource.updates[0]["addParents"] == "folder-1"
    assert drive.resource.updates[0]["removeParents"] == "root"


def test_google_adapter_update_deletes_old_body_before_inserting() -> None:
    docs = DocsService()
    drive = DriveService()
    publisher = GoogleDocsPublisher(docs_service=docs, drive_service=drive)
    content = DocumentContent("Title", (DocumentBlock("New body"),))

    publisher.replace("doc-1", content)

    requests = docs.resource.batches[0]["body"]["requests"]
    assert requests[0]["deleteContentRange"]["range"] == {
        "startIndex": 1,
        "endIndex": 24,
    }
    assert requests[1]["insertText"]["text"] == "New body\n"
    assert drive.resource.updates[0]["body"] == {"name": "Title"}


def test_google_credentials_must_be_desktop_type(tmp_path: Path) -> None:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    invalid = tmp_path / "web.json"
    invalid.write_text(json.dumps({"web": {"client_id": "x"}}), encoding="utf-8")

    with pytest.raises(GoogleAuthError, match="Desktop"):
        install_client_credentials(invalid, paths)

    desktop = tmp_path / "desktop.json"
    desktop.write_text(json.dumps({"installed": {"client_id": "x"}}), encoding="utf-8")
    stored = install_client_credentials(desktop, paths)

    assert stored == paths.google_credentials_file
    assert stored.stat().st_mode & 0o777 == 0o600
