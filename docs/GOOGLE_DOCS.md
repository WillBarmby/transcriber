# Google Docs publication

tranpro can publish any saved transcript as a native Google Doc. Publication is
optional and explicit: transcription never sends content to Google on its own.

## One-time Google setup

In a Google Cloud project:

1. Enable the Google Docs API and Google Drive API.
2. Configure the OAuth consent screen for an external or internal app.
3. Add your Google account as a test user if the app remains in testing.
4. Create an OAuth client with application type **Desktop app**.
5. Download its JSON file, then install and authorize it:

```shell
tp google setup --credentials ~/Downloads/client_secret.json
tp google authorize
```

Authorization opens Google's consent page in a browser and returns through a
temporary local callback. tranpro requests only the Docs scope and Drive's
per-file scope. The refresh token is stored in the operating-system Keychain,
not in SQLite or `config.toml`. The downloaded OAuth client configuration is
copied with private permissions into tranpro's application-data directory.

Google's official setup references are the
[Docs API quickstart](https://developers.google.com/workspace/docs/api/quickstart/python)
and [Drive API scope guide](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).

## Publishing

The default output contains the preferred transcript only:

```shell
tp publish RECORDING_ID
```

Add the latest successful grounded summary for that same transcript, override
the document title, or place a newly created document in a Drive folder:

```shell
tp publish RECORDING_ID --with-summary
tp publish RECORDING_ID --with-timestamps
tp publish RECORDING_ID --title "Interview notes"
tp publish RECORDING_ID --folder GOOGLE_DRIVE_FOLDER_ID
```

Published Docs omit timestamps for a cleaner reading experience. Pass
`--with-timestamps` to add transcript timestamps and validated summary evidence
markers rendered by tranpro after model output. The Google Doc uses native title,
subtitle, and heading styles, so its outline and formatting remain editable.

Publishing identical content again returns the existing document without a
network write. To deliberately replace the body of the latest Google Doc and
append a new local snapshot:

```shell
tp publish RECORDING_ID --update
tp publish RECORDING_ID --with-summary --update
```

`--update` changes the document body and file title; it does not move the existing
document to a different folder. Use `tp show RECORDING_ID` to inspect
the immutable publication history and URLs.

To remove tranpro's stored refresh token:

```shell
tp google disconnect
```

This does not delete OAuth client configuration or published documents. Access
can also be revoked from the Google Account security settings.
