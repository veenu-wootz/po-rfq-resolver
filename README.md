# PO RFQ Folder ID Resolver

Small FastAPI service used by the Purchase Order workflow in Glide.

Glide sends the projects a user selected for a PO. This service looks up the
RFQ Folder ID of each project in the Glide Big Table, joins them into one
comma-separated string, and triggers the Power Automate flow that copies the
PO attachments into each RFQ folder.

```
Glide  ->  POST /resolve-rfq-and-trigger  ->  Glide queryTables  ->  Power Automate
```

## Endpoint

`POST /resolve-rfq-and-trigger`

```json
{
  "selected_projects": "Entai 37,Akron 11,Entai 39",
  "google_attachments_id": "<Google Drive folder ID from Glide>",
  "row_id": "<Purchase Order row ID from Glide>"
}
```

`selected_projects` is `"<Customer name> <RFQ Sequence>"` items separated by
commas. The RFQ Sequence is always the last whitespace-separated token, so
customer names may contain spaces and dashes (`Test - 2 1016`).

Responses:

| Status | Meaning |
|---|---|
| 200 | All projects resolved, Power Automate triggered. Body includes `rfq_folder_ids`. |
| 400 | A project name could not be split into customer + sequence. |
| 422 | At least one project has no RFQ Folder ID (Power Automate is **not** triggered). |
| 502 | Glide or Power Automate returned an error. |

## Configuration

Two environment variables (or a `.env` file next to the script — never commit it):

| Variable | Value |
|---|---|
| `GLIDE_API_TOKEN` | Glide API bearer token |
| `POWER_AUTOMATE_URL` | Full signed URL of the flow's *When an HTTP request is received* trigger |

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in the values
uvicorn PO_RFQFolderID_Script:app --reload --port 8000
```

## Deploy on Render

`render.yaml` defines the web service. Set `GLIDE_API_TOKEN` and
`POWER_AUTOMATE_URL` in the Render dashboard (they are marked `sync: false`).

## Notes on the Glide query

Glide's `queryTables` SQL dialect is limited: it rejects `(a AND b) OR (c AND d)`,
`IN (...)`, and explicit column lists. The service therefore sends one exact
`WHERE "BietT" = $1 AND "TsFhb" = $2` query per project, all inside a single
request, and flattens the per-query results.
