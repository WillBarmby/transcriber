"""Google Docs and Drive API adapter."""

from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tranpro.publication.auth import load_credentials
from tranpro.publication.models import DocumentContent, RemoteDocument
from tranpro.publication.render import google_batch_requests


class PublicationError(RuntimeError):
    """Raised when a remote document cannot be published safely."""


class GoogleDocsPublisher:
    @property
    def name(self) -> str:
        return "google-docs"

    def __init__(
        self,
        *,
        docs_service: Any | None = None,
        drive_service: Any | None = None,
    ) -> None:
        if docs_service is None or drive_service is None:
            credentials = load_credentials()
            docs_service = build(
                "docs", "v1", credentials=credentials, cache_discovery=False
            )
            drive_service = build(
                "drive", "v3", credentials=credentials, cache_discovery=False
            )
        self.docs = docs_service
        self.drive = drive_service

    def create(
        self, content: DocumentContent, *, folder_id: str | None = None
    ) -> RemoteDocument:
        document_id: str | None = None
        try:
            created = (
                self.docs.documents().create(body={"title": content.title}).execute()
            )
            document_id = str(created["documentId"])
            self.docs.documents().batchUpdate(
                documentId=document_id,
                body={"requests": google_batch_requests(content)},
            ).execute()
            if folder_id:
                self._move_to_folder(document_id, folder_id)
        except (HttpError, KeyError, OSError) as error:
            if document_id is not None:
                self._trash_best_effort(document_id)
            raise PublicationError(
                f"Google Docs publication failed: {error}"
            ) from error
        return RemoteDocument(document_id, _document_url(document_id))

    def replace(self, document_id: str, content: DocumentContent) -> RemoteDocument:
        try:
            document = self.docs.documents().get(documentId=document_id).execute()
            body = document.get("body", {})
            elements = body.get("content", [])
            end_index = int(elements[-1].get("endIndex", 1)) if elements else 1
            self.docs.documents().batchUpdate(
                documentId=document_id,
                body={
                    "requests": google_batch_requests(
                        content, delete_end_index=max(1, end_index - 1)
                    )
                },
            ).execute()
            self.drive.files().update(
                fileId=document_id,
                body={"name": content.title},
                fields="id,name",
            ).execute()
        except (HttpError, KeyError, TypeError, ValueError) as error:
            raise PublicationError(f"Google Docs update failed: {error}") from error
        return RemoteDocument(document_id, _document_url(document_id))

    def _move_to_folder(self, document_id: str, folder_id: str) -> None:
        metadata = (
            self.drive.files().get(fileId=document_id, fields="parents").execute()
        )
        parents = ",".join(metadata.get("parents", []))
        self.drive.files().update(
            fileId=document_id,
            addParents=folder_id,
            removeParents=parents or None,
            fields="id,parents",
        ).execute()

    def _trash_best_effort(self, document_id: str) -> None:
        try:
            self.drive.files().update(
                fileId=document_id, body={"trashed": True}, fields="id,trashed"
            ).execute()
        except Exception:
            return


def _document_url(document_id: str) -> str:
    return f"https://docs.google.com/document/d/{document_id}/edit"
