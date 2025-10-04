#!/usr/bin/env python3
import os
from pathlib import Path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from config.paths import TEXT_DIR, FINAL_DIR

# --- CONFIG ---
BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = BASE_DIR / "config" / "credentials.json"
TOKEN_FILE = BASE_DIR / "config" / "token.pickle"

# 👇 paste your Drive folder ID
FOLDER_ID = "1StJCw_R8G2tVUEgI3N32TODJfdX8BAgF"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


def get_creds():
    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)
    return creds


creds = get_creds()
drive_service = build("drive", "v3", credentials=creds)
docs_service = build("docs", "v1", credentials=creds)


# --- DOC CREATION ---
def create_doc_in_folder(title, folder_id):
    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    file = drive_service.files().create(
        body=file_metadata,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return file["id"]


def fill_doc(doc_id, title, summary, transcript):
    requests = []
    doc_end = 1

    def add_text(text):
        nonlocal doc_end
        requests.append(
            {
                "insertText": {
                    "endOfSegmentLocation": {"segmentId": ""},
                    "text": text,
                }
            }
        )
        start_index = doc_end
        doc_end += len(text)
        return start_index, doc_end

    title_start, title_end = add_text(f"{title}\n")
    requests.append(
        {
            "updateParagraphStyle": {
                "range": {"startIndex": title_start, "endIndex": title_end},
                "paragraphStyle": {"namedStyleType": "TITLE"},
                "fields": "namedStyleType",
            }
        }
    )

    add_text("\n")

    summary_start, summary_end = add_text("Summary\n")
    requests.append(
        {
            "updateParagraphStyle": {
                "range": {"startIndex": summary_start, "endIndex": summary_end},
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                "fields": "namedStyleType",
            }
        }
    )

    add_text(f"{summary}\n\n")

    transcript_heading_start, transcript_heading_end = add_text("Transcript\n")
    requests.append(
        {
            "updateParagraphStyle": {
                "range": {
                    "startIndex": transcript_heading_start,
                    "endIndex": transcript_heading_end,
                },
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                "fields": "namedStyleType",
            }
        }
    )

    add_text(f"{transcript}\n")
    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()
    return f"https://docs.google.com/document/d/{doc_id}/edit"


# --- MAIN WORKFLOW ---
def main():
    transcript_files = {f.name: f for f in TEXT_DIR.glob("*.txt")}
    summary_files = {f.name: f for f in FINAL_DIR.glob("*.txt")}

    matches = set(transcript_files.keys()) & set(summary_files.keys())
    if not matches:
        print("No matching transcript/summary pairs found.")
        return

    for fname in sorted(matches):
        with open(summary_files[fname], "r") as f:
            summary = f.read().strip()
        with open(transcript_files[fname], "r") as f:
            transcript = f.read().strip()

        title = fname.replace(".txt", "").title()
        doc_id = create_doc_in_folder(title, FOLDER_ID)
        link = fill_doc(doc_id, title, summary, transcript)
        print(f"[OK] Created doc for {fname}: {link}")


if __name__ == "__main__":
    main()
