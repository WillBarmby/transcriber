from pathlib import Path

import pytest

from tranpro.library.database import Database
from tranpro.library.models import Segment, SummarySection
from tranpro.library.repository import LibraryRepository
from tranpro.paths import AppPaths
from tranpro.publication.models import DocumentBlock, DocumentContent, RemoteDocument
from tranpro.publication.render import google_batch_requests, render_document
from tranpro.publication.service import PublicationService


class FakePublisher:
    def __init__(self) -> None:
        self.created: list[DocumentContent] = []
        self.replaced: list[tuple[str, DocumentContent]] = []

    @property
    def name(self) -> str:
        return "google-docs"

    def create(
        self, content: DocumentContent, *, folder_id: str | None = None
    ) -> RemoteDocument:
        self.created.append(content)
        assert folder_id in (None, "folder-1")
        return RemoteDocument("doc-1", "https://docs.google.com/document/d/doc-1/edit")

    def replace(self, document_id: str, content: DocumentContent) -> RemoteDocument:
        self.replaced.append((document_id, content))
        return RemoteDocument(
            document_id, f"https://docs.google.com/document/d/{document_id}/edit"
        )


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[LibraryRepository, Path, int]:
    paths = AppPaths(data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")
    repository = LibraryRepository(Database(paths))
    source = tmp_path / "interview.mp3"
    source.write_bytes(b"audio")
    recording, _ = repository.register_recording(source)
    transcript = repository.add_transcript(
        recording.id,
        provider="test",
        model="test",
        segments=[Segment(0, 5_000, 6_000, "A grounded statement.", "Host")],
    )
    return repository, source, transcript.id


def test_document_rendering_omits_timestamps_by_default() -> None:
    content = render_document(
        source=Path("lecture.mp3"),
        segments=(Segment(0, 5_000, 6_000, "Statement", "Ada"),),
        summary_sections=(
            SummarySection("Key concepts", "Scarcity matters.", ("s000001",)),
        ),
    )

    requests = google_batch_requests(content)

    assert content.title == "lecture"
    assert "Transcript evidence" not in content.plain_text
    assert "[00:05]" not in content.plain_text
    assert "Ada: Statement" in content.plain_text
    assert requests[0]["insertText"]["location"] == {"index": 1}  # type: ignore[index]
    styles = [
        request["updateParagraphStyle"]["paragraphStyle"]["namedStyleType"]  # type: ignore[index]
        for request in requests[1:]
    ]
    assert styles[:4] == ["TITLE", "SUBTITLE", "HEADING_1", "HEADING_2"]


def test_document_rendering_can_include_grounded_timestamps() -> None:
    content = render_document(
        source=Path("lecture.mp3"),
        segments=(Segment(0, 5_000, 6_000, "Statement", "Ada"),),
        summary_sections=(
            SummarySection("Key concepts", "Scarcity matters.", ("s000001",)),
        ),
        with_timestamps=True,
    )

    assert "Transcript evidence: 00:05 (s000001)" in content.plain_text
    assert "[00:05] Ada: Statement" in content.plain_text


def test_google_style_indices_count_utf16_code_units() -> None:
    content = DocumentContent("Emoji", (DocumentBlock("A 😀", "TITLE"),))

    requests = google_batch_requests(content)

    assert requests[1]["updateParagraphStyle"]["range"] == {  # type: ignore[index]
        "startIndex": 1,
        "endIndex": 6,
    }


def test_publication_reuses_exact_content_and_updates_only_explicitly(
    seeded: tuple[LibraryRepository, Path, int],
) -> None:
    repository, _, _ = seeded
    publisher = FakePublisher()
    service = PublicationService(publisher=publisher, repository=repository)

    first = service.publish(1, folder_id="folder-1")
    reused = service.publish(1)
    updated = service.publish(1, update=True, title="Revised title")

    assert first.reused is False
    assert reused.reused is True
    assert updated.updated is True
    assert len(publisher.created) == 1
    assert "[00:05]" not in publisher.created[0].plain_text
    assert publisher.replaced[0][0] == "doc-1"
    assert publisher.replaced[0][1].blocks[0].text == "Revised title"
    publications = repository.list_publications(1)
    assert len(publications) == 2
    assert publications[0].title == "Revised title"


def test_publication_can_include_summary_for_same_transcript(
    seeded: tuple[LibraryRepository, Path, int],
) -> None:
    repository, _, transcript_id = seeded
    repository.add_summary(
        transcript_id,
        provider="test",
        model="test",
        sections=[SummarySection("Overview", "Notes", ("s000001",))],
    )
    publisher = FakePublisher()

    outcome = PublicationService(publisher=publisher, repository=repository).publish(
        1, with_summary=True
    )

    assert outcome.reused is False
    assert "Overview" in publisher.created[0].plain_text
    assert repository.list_publications(1)[0].summary_id == 1
