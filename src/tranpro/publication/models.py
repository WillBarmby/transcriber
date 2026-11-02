"""Provider-independent publication values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    text: str
    named_style: str = "NORMAL_TEXT"


@dataclass(frozen=True, slots=True)
class DocumentContent:
    title: str
    blocks: tuple[DocumentBlock, ...]

    @property
    def plain_text(self) -> str:
        return "".join(f"{block.text.rstrip()}\n" for block in self.blocks)


@dataclass(frozen=True, slots=True)
class RemoteDocument:
    id: str
    url: str


@dataclass(frozen=True, slots=True)
class PublicationOutcome:
    publication_id: int
    remote_id: str
    url: str
    reused: bool
    updated: bool
