"""
Azure routes: /export_azure, /fields_azure, /generate_azure
"""
from datetime import datetime

import requests
from flask import Blueprint, request, render_template, flash, redirect

from integrations.azure_client import export_azure_work_items, _build_headers
from config.constants import AZURE_API_VERSION, DEFAULT_AZURE_FIELDS

bp = Blueprint("azure", __name__)


@bp.route("/export_azure")
def export_azure():
    return render_template("export_azure.html")


@bp.route("/fields_azure", methods=["POST"])
def fetch_fields_azure():
    org_url = request.form["org_url"].rstrip("/")
    project = request.form["project"]
    pat = request.form["pat"]

    headers = _build_headers(pat)

    # Fetch work item types
    wit_url = f"{org_url}/{project}/_apis/wit/workitemtypes?api-version={AZURE_API_VERSION}"
    resp = requests.get(wit_url, headers=headers)
    if resp.status_code != 200:
        return render_template("export_azure.html", error=f"Failed to fetch work item types (HTTP {resp.status_code}).")

    work_item_types = sorted([w["name"] for w in resp.json().get("value", [])])

    # Fetch fields
    fields_url = f"{org_url}/{project}/_apis/wit/fields?api-version={AZURE_API_VERSION}"
    resp = requests.get(fields_url, headers=headers)
    if resp.status_code != 200:
        return render_template("export_azure.html", error=f"Failed to fetch fields (HTTP {resp.status_code}).")

    custom_fields = sorted(resp.json().get("value", []), key=lambda f: f.get("name", "").lower())

    return render_template(
        "export_azure.html",
        custom_fields=custom_fields,
        work_item_types=work_item_types,
        org_url=org_url,
        project=project,
        pat=pat
    )


@bp.route("/generate_azure", methods=["POST"])
def generate_azure():
    try:
        org_url = request.form["org_url"]
        project = request.form["project"]
        pat = request.form["pat"]
        work_item_types = request.form.getlist("witype")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{project}_azure_{timestamp}.json"

        export_azure_work_items(
            org_url=org_url,
            project=project,
            pat=pat,
            fields_to_include=DEFAULT_AZURE_FIELDS,
            work_item_types=work_item_types,
            timestamp=timestamp
        )

        flash(f"Azure export successful: {filename}", "success")

    except Exception as e:
        flash(f"Azure export failed: {str(e)}", "danger")

    return redirect("/")
