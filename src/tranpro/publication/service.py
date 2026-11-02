"""Publication orchestration with immutable local snapshots."""

from __future__ import annotations

import hashlib
from typing import Protocol

from tranpro.library.models import SummarySection
from tranpro.library.repository import LibraryRepository
from tranpro.publication.models import (
    DocumentBlock,
    DocumentContent,
    PublicationOutcome,
    RemoteDocument,
)
from tranpro.publication.render import render_document


class DocumentPublisher(Protocol):
    @property
    def name(self) -> str: ...

    def create(
        self, content: DocumentContent, *, folder_id: str | None = None
    ) -> RemoteDocument: ...

    def replace(self, document_id: str, content: DocumentContent) -> RemoteDocument: ...


class PublicationService:
    def __init__(
        self, *, publisher: DocumentPublisher, repository: LibraryRepository
    ) -> None:
        self.publisher = publisher
        self.repository = repository

    def publish(
        self,
        recording_id: int,
        *,
        with_summary: bool = False,
        update: bool = False,
        title: str | None = None,
        folder_id: str | None = None,
    ) -> PublicationOutcome:
        recording = self.repository.get_recording(recording_id)
        transcript = self.repository.get_preferred_transcript(recording_id)
        segments = tuple(self.repository.get_segments(transcript.id))
        summary = None
        summary_sections: tuple[SummarySection, ...] = ()
        if with_summary:
            summary = self.repository.get_latest_successful_summary(recording_id)
            if summary.transcript_id != transcript.id:
                raise ValueError(
                    "Latest summary does not belong to the preferred transcript; "
                    "select or regenerate a summary before publishing"
                )
            summary_sections = tuple(self.repository.get_summary_sections(summary.id))
        source = recording.current_path or recording.original_path
        content = render_document(
            source=source,
            segments=segments,
            summary_sections=summary_sections,
        )
        if title:
            content = DocumentContent(
                title=title,
                blocks=(DocumentBlock(title, "TITLE"), *content.blocks[1:]),
            )
        digest = _content_hash(content)
        if not update:
            existing = self.repository.find_publication_by_content(
                self.publisher.name, digest
            )
            if existing is not None:
                return PublicationOutcome(
                    existing.id,
                    existing.remote_id,
                    existing.remote_url,
                    reused=True,
                    updated=False,
                )
            remote = self.publisher.create(content, folder_id=folder_id)
        else:
            previous = self.repository.get_latest_publication(
                recording_id, provider=self.publisher.name
            )
            remote = self.publisher.replace(previous.remote_id, content)
        publication = self.repository.record_publication(
            recording_id=recording.id,
            transcript_id=transcript.id,
            summary_id=None if summary is None else summary.id,
            provider=self.publisher.name,
            remote_id=remote.id,
            remote_url=remote.url,
            title=content.title,
            content_hash=digest,
        )
        return PublicationOutcome(
            publication.id,
            remote.id,
            remote.url,
            reused=False,
            updated=update,
        )


def _content_hash(content: DocumentContent) -> str:
    digest = hashlib.sha256()
    digest.update(content.title.encode())
    digest.update(b"\0")
    for block in content.blocks:
        digest.update(block.named_style.encode())
        digest.update(b"\0")
        digest.update(block.text.encode())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"
