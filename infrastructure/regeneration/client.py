"""
Argo Workflows regeneration client.

Triggers a shard-regeneration workflow for a given file segment.
The file_repo dependency replaces the old `app.database` global.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
# from argo.workflows.client import (
#     ApiClient,
#     Configuration,
#     V1alpha1WorkflowCreateRequest,
#     WorkflowServiceApi,
# )

from core.repositories import IFileRepository

logger = logging.getLogger(__name__)

_WORKFLOW_MANIFEST = Path(__file__).parent.parent.parent / "regeneration-workflow.yaml"


class RegenerationClient:
    def __init__(self, file_repo: IFileRepository) -> None:
        self._files = file_repo

    # def start_regeneration_job(self, file_id: str, seg_no: int) -> None:
    #     seg_no = int(seg_no)
    #     host = os.environ.get("ARGO_URI")
    #     if not host:
    #         logger.error("ARGO_URI environment variable is not set.")
    #         return
    #
    #     file = self._files.find_by_id(str(file_id))
    #     if not file:
    #         logger.error("Regeneration: file %s not found.", file_id)
    #         return
    #
    #     regeneration_count = file.segments[seg_no].get("regeneration_count", 0)
    #
    #     try:
    #         with open(_WORKFLOW_MANIFEST) as f:
    #             manifest: dict = yaml.safe_load(f)
    #     except FileNotFoundError:
    #         logger.error("Regeneration workflow manifest not found at %s.", _WORKFLOW_MANIFEST)
    #         return
    #
    #     manifest["metadata"]["name"] = (
    #         f"{str(file_id).lower()}cera{seg_no}cera{regeneration_count}"
    #     )
    #     manifest["spec"]["templates"][0]["inputs"]["parameters"][0]["value"] = str(file_id)
    #     manifest["spec"]["templates"][0]["inputs"]["parameters"][1]["value"] = str(seg_no)
    #
    #     config = Configuration(host=host)
    #     client = ApiClient(configuration=config)
    #     service = WorkflowServiceApi(api_client=client)
    #
    #     try:
    #         service.create_workflow("argo", V1alpha1WorkflowCreateRequest(workflow=manifest))
    #     except Exception:
    #         logger.exception("Failed to create regeneration workflow for file %s seg %s.", file_id, seg_no)

    def start_regeneration_job(self, file_id: str, seg_no: int) -> None:
        NotImplementedError()