from collections import defaultdict
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import unquote, urlparse

import httpx

from config import BaseConfig
from core.domain.models import (
    TaskParents,
    WorkflowTemplate,
)


class WorkflowProcessor:
    BASE_DIR = Path(BaseConfig.KEYSTORE_DIR).parent / "downloads"

    @staticmethod
    def load_workflow_template(json_path: str) -> WorkflowTemplate:
        with open(json_path, "r") as f:
            # TODO: Update all models having recursive models
            workflow_template_dict = json.loads(f.read())
            workflow_template_dict["tasks"] = list(
                map(
                    lambda x: TaskParents(**x), workflow_template_dict["tasks"]
                )
            )
            return WorkflowTemplate(**workflow_template_dict)

    @staticmethod
    def build_scheduler_outputs(
        workflow: WorkflowTemplate,
    ) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
        children_per_node = defaultdict(list)
        edges = {}
        tasks = workflow.tasks
        for task in tasks:
            edges[task.task_id] = task.parents
        for child, parents in edges.items():
            for parent in parents:
                children_per_node[parent].append(child)

        return dict(children_per_node), edges

    @staticmethod
    def download_workflow_package(url: str, workflow_id: str) -> Path:
        os.makedirs(WorkflowProcessor.BASE_DIR, exist_ok=True)
        file_name = unquote(Path(urlparse(url).path).name)
        file_path = WorkflowProcessor.BASE_DIR / workflow_id / file_name
        response = httpx.get(url)
        response.raise_for_status()
        file_path.write_bytes(response.content)
        return file_path
