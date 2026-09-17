import os
import re
from typing import List, Dict, Any

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# ============================================================
# CONFIGURATION
# ============================================================

# Load secrets from a .env file sitting next to this script
# (GLIDE_API_TOKEN, POWER_AUTOMATE_URL). Real environment variables
# always take precedence over the .env file. If python-dotenv is not
# installed, we silently fall back to plain environment variables.
try:
    from dotenv import load_dotenv

    load_dotenv(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        override=False,
    )
except ImportError:
    pass

GLIDE_QUERY_URL = "https://api.glideapp.io/api/function/queryTables"

# Already known from your Glide API example.
GLIDE_APP_ID = "rIdnwOvTnxdsQUtlXKUB"

GLIDE_TABLE_NAME = (
    "native-table-24696dcc-caaf-4bf8-a015-1e9ef394aa1b"
)

# Do NOT hardcode the Glide token in source code.
# Set environment variable:
# GLIDE_API_TOKEN=your-secret-token
GLIDE_API_TOKEN = os.getenv("GLIDE_API_TOKEN", "")


# IMPORTANT:
# Put your actual Power Automate trigger URL in an environment variable.
#
# POWER_AUTOMATE_URL=https://.......
#
# I am deliberately not embedding the signed URL directly in source code.
POWER_AUTOMATE_URL = os.getenv("POWER_AUTOMATE_URL", "")


# Glide basic-column IDs
COL_CUSTOMER_NAME = "BietT"
COL_RFQ_SEQUENCE = "TsFhb"
COL_RFQ_FOLDER_ID = "Q7vEH"


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="PO RFQ Resolver",
    version="1.0.0"
)


# ============================================================
# INPUT MODEL
# ============================================================

class PORequest(BaseModel):
    # Expected:
    # "Entai 37,Akron 11,Entai 39"
    selected_projects: str = Field(
        ...,
        description="Comma-separated selected Glide project names"
    )

    # You said Glide will supply these two values.
    google_attachments_id: str

    row_id: str


# ============================================================
# HELPERS
# ============================================================

def normalise(value: Any) -> str:
    """
    Normalize strings for comparison.
    """
    if value is None:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def parse_selected_projects(selected_projects: str) -> List[Dict[str, str]]:
    """
    Converts:
        "Entai 37,Akron 11,Entai 39"

    into:
        [
            {"project_name": "Entai 37",
             "customer_name": "Entai",
             "rfq_sequence": "37"},
            ...
        ]

    IMPORTANT ASSUMPTION:
    RFQ Sequence is always the FINAL whitespace-separated portion
    of Project Name.

    This still supports customers containing spaces:

        "ABC Industries India 37"

    becomes:

        customer_name = "ABC Industries India"
        rfq_sequence  = "37"

    If RFQ Sequence itself can contain spaces, this parser needs
    to be changed.
    """

    raw_projects = [
        p.strip()
        for p in selected_projects.split(",")
        if p.strip()
    ]

    if not raw_projects:
        raise ValueError("No projects supplied.")

    result = []

    for project in raw_projects:
        parts = project.rsplit(" ", 1)

        if len(parts) != 2:
            raise ValueError(
                f"Cannot split project '{project}' into "
                f"Customer Name + RFQ Sequence."
            )

        customer_name = parts[0].strip()
        rfq_sequence = parts[1].strip()

        if not customer_name or not rfq_sequence:
            raise ValueError(
                f"Invalid project format: '{project}'"
            )

        result.append(
            {
                "project_name": project,
                "customer_name": customer_name,
                "rfq_sequence": rfq_sequence,
            }
        )

    return result


def build_glide_query(
    projects: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Build ONE Glide request containing ONE exact query per project.

    Glide's queryTables SQL dialect is very limited (verified live):
      - "col" = $1 AND "col2" = $2            -> OK
      - "col" = $1 OR "col" = $2              -> OK (same column only)
      - (a AND b) OR (c AND d)                -> 400 Invalid SQL query
      - IN (...)                              -> 400 Invalid SQL query
      - SELECT "col1","col2" (explicit cols)  -> 400 Invalid SQL query
      - several queries in one request        -> OK

    So instead of an OR-chain we send:

    queries: [
      {sql: SELECT * FROM "t" WHERE "BietT" = $1 AND "TsFhb" = $2 LIMIT 1000,
       params: ["Entai", "37"]},
      {sql: ..., params: ["Akron", "11"]},
      ...
    ]

    Glide answers with one {"rows": [...]} object per query, in order.
    """

    sql = (
        f'SELECT * FROM "{GLIDE_TABLE_NAME}" '
        f'WHERE "{COL_CUSTOMER_NAME}" = $1 '
        f'AND "{COL_RFQ_SEQUENCE}" = $2 '
        f'LIMIT 1000'
    )

    queries = [
        {
            "sql": sql,
            "params": [
                project["customer_name"],
                project["rfq_sequence"],
            ],
        }
        for project in projects
    ]

    return {
        "appID": GLIDE_APP_ID,
        "queries": queries,
    }


def query_glide(
    projects: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """
    Query only matching rows from Glide Big Table.
    """

    if not GLIDE_API_TOKEN:
        raise RuntimeError(
            "GLIDE_API_TOKEN environment variable is missing."
        )

    payload = build_glide_query(projects)

    response = requests.post(
        GLIDE_QUERY_URL,
        headers={
            "Authorization": f"Bearer {GLIDE_API_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Glide API error {response.status_code}: "
            f"{response.text}"
        )

    data = response.json()

    # --------------------------------------------------------
    # Verified live: Glide returns a list with one object per
    # query we sent, each shaped {"rows": [...]}.
    #
    #   [ {"rows": [row, ...]}, {"rows": [row, ...]}, ... ]
    #
    # We flatten the rows of ALL results into one list. A few
    # alternative shapes are still handled defensively.
    # --------------------------------------------------------

    rows: List[Dict[str, Any]] = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "rows" in item:
                rows.extend(item["rows"] or [])
            elif isinstance(item, dict) and "data" in item:
                rows.extend(item["data"] or [])
            elif isinstance(item, dict):
                # Fallback if Glide directly returns row objects.
                rows.append(item)

    elif isinstance(data, dict):

        if "rows" in data:
            rows = data["rows"]

        elif "data" in data:
            inner = data["data"]

            if isinstance(inner, list):
                rows = inner

    if not isinstance(rows, list):
        raise RuntimeError(
            f"Unexpected Glide response structure: {data}"
        )

    return rows


def resolve_rfq_folder_ids(
    requested_projects: List[Dict[str, str]],
    glide_rows: List[Dict[str, Any]],
):
    """
    Build Project Name again from the Glide values and match it
    against the original selected project list.

    Returns:
        ordered_folder_ids
        matched_projects
        missing_projects
    """

    requested_lookup = {
        normalise(p["project_name"]): p["project_name"]
        for p in requested_projects
    }

    matches_by_project = {}

    for row in glide_rows:

        customer_name = str(
            row.get(COL_CUSTOMER_NAME, "")
        ).strip()

        rfq_sequence = str(
            row.get(COL_RFQ_SEQUENCE, "")
        ).strip()

        folder_id = row.get(COL_RFQ_FOLDER_ID)

        generated_project_name = (
            f"{customer_name} {rfq_sequence}"
        ).strip()

        key = normalise(generated_project_name)

        if key not in requested_lookup:
            continue

        if not folder_id:
            continue

        folder_id = str(folder_id).strip()

        if not folder_id:
            continue

        # Store possible duplicates so we can detect them.
        matches_by_project.setdefault(key, []).append(folder_id)

    ordered_folder_ids = []
    matched_projects = []
    missing_projects = []
    duplicate_projects = {}

    # Preserve the exact order Glide sent.
    for project in requested_projects:
        key = normalise(project["project_name"])

        folder_ids = matches_by_project.get(key, [])

        # Remove duplicate folder IDs while maintaining order.
        unique_folder_ids = list(dict.fromkeys(folder_ids))

        if not unique_folder_ids:
            missing_projects.append(project["project_name"])
            continue

        if len(unique_folder_ids) > 1:
            duplicate_projects[project["project_name"]] = (
                unique_folder_ids
            )

        # Current business rule:
        # use the first matching RFQ Folder ID.
        #
        # FLAG:
        # Change this if one project can legitimately map to
        # multiple RFQ Folder IDs.
        chosen_folder_id = unique_folder_ids[0]

        ordered_folder_ids.append(chosen_folder_id)
        matched_projects.append(project["project_name"])

    # Remove any repeated folder IDs globally while preserving order.
    ordered_folder_ids = list(
        dict.fromkeys(ordered_folder_ids)
    )

    return {
        "folder_ids": ordered_folder_ids,
        "matched_projects": matched_projects,
        "missing_projects": missing_projects,
        "duplicate_projects": duplicate_projects,
    }


def trigger_power_automate(
    google_attachments_id: str,
    rfq_folder_ids_csv: str,
    row_id: str,
):
    """
    Trigger Power Automate.
    """

    if not POWER_AUTOMATE_URL:
        raise RuntimeError(
            "POWER_AUTOMATE_URL environment variable is missing."
        )

    # ========================================================
    # POWER AUTOMATE REQUEST BODY
    #
    # FLAG:
    # You gave these as the three Power Automate variables.
    # I have used their names literally.
    #
    # If your HTTP trigger schema uses internal names such as
    # googleAttachmentsId / rfqFolderId / rowId,
    # change the keys here.
    # ========================================================

    payload = {
        "Google Attachments ID": google_attachments_id,
        "RFQ Folder ID": rfq_folder_ids_csv,
        "Row ID": row_id,
    }

    response = requests.post(
        POWER_AUTOMATE_URL,
        headers={
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Power Automate returned "
            f"{response.status_code}: {response.text}"
        )

    # Power Automate may return an empty response.
    try:
        body = response.json()
    except ValueError:
        body = response.text

    return {
        "status_code": response.status_code,
        "response": body,
    }


# ============================================================
# MAIN ENDPOINT
# ============================================================

@app.post("/resolve-rfq-and-trigger")
def resolve_rfq_and_trigger(request: PORequest):

    # 1. Parse Glide selected projects
    try:
        projects = parse_selected_projects(
            request.selected_projects
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    # 2. Query only relevant RFQ records
    try:
        glide_rows = query_glide(projects)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Glide query failed: {exc}",
        )

    # 3. Resolve RFQ Folder IDs
    result = resolve_rfq_folder_ids(
        requested_projects=projects,
        glide_rows=glide_rows,
    )

    # --------------------------------------------------------
    # BUSINESS RULE:
    #
    # Do NOT trigger Power Automate if even one selected
    # project has no corresponding RFQ Folder ID.
    #
    # This protects against silently sending incomplete data.
    #
    # Change this behavior if partial matching is acceptable.
    # --------------------------------------------------------

    if result["missing_projects"]:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "RFQ Folder ID could not be resolved "
                    "for all selected projects."
                ),
                "missing_projects": result["missing_projects"],
                "matched_projects": result["matched_projects"],
            },
        )

    if not result["folder_ids"]:
        raise HTTPException(
            status_code=422,
            detail="No RFQ Folder IDs were found.",
        )

    # 4. Create comma-separated string
    rfq_folder_ids_csv = ",".join(
        result["folder_ids"]
    )

    # 5. Trigger Power Automate
    try:
        power_automate_result = trigger_power_automate(
            google_attachments_id=request.google_attachments_id,
            rfq_folder_ids_csv=rfq_folder_ids_csv,
            row_id=request.row_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Power Automate failed: {exc}",
        )

    # 6. Return useful status to Glide
    return {
        "success": True,
        "selected_projects": [
            p["project_name"]
            for p in projects
        ],
        "rfq_folder_ids": rfq_folder_ids_csv,
        "matched_projects": result["matched_projects"],
        "duplicate_projects": result["duplicate_projects"],
        "power_automate": power_automate_result,
    }