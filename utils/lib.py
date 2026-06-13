from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from core.domain.models import ActiveComputeNode, TaskPayload


def extract_zip_file(zip_path: Path) -> Path:
    if not zip_path.is_file():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")
    parent_dir = zip_path.parent
    with ZipFile(zip_path, 'r') as zf:
        zf.extractall(parent_dir)
    zip_path.unlink()
    return parent_dir


def zip_directory(parent_dir: Path, task_id: str) -> Path:
    source = parent_dir.resolve()
    if not source.is_dir():
        raise ValueError(f"Directory {source} does not exist")
    output_zip = source / f"task_{task_id}.zip"
    with ZipFile(output_zip, "w", ZIP_DEFLATED) as zf:
        for file_path in source.rglob(f'*_{task_id}'):
            if file_path.suffix.lower() == ".zip":
                continue
            arcname = file_path.relative_to(source)
            zf.write(file_path, arcname)
    return output_zip


class NodeScoreCalculator:
    @staticmethod
    def _ipv4_to_int(ipv4: str) -> int:
        p = list(map(int, ipv4.split(".")))
        return (p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3]

    @staticmethod
    def _nodes_proximity_score(ip_a: str, ip_b: str) -> float:
        xor = NodeScoreCalculator._ipv4_to_int(
            ip_a
        ) ^ NodeScoreCalculator._ipv4_to_int(ip_b)
        leading_zeros = 32 - xor.bit_length() if xor else 32
        return leading_zeros / 32.0

    @staticmethod
    def node_score(
        task: TaskPayload,
        node: ActiveComputeNode,
        task_requester_ip: str,
        alpha=0.75,
        beta=0.25,
    ) -> float:
        if (
            node.available_ram_mb < task.resources.ram_mb
            or node.cpu_cores < task.resources.cpu_cores
        ):
            return float('-inf')

        res = (
            (node.cpu_cores - task.resources.cpu_cores) / node.cpu_cores
            + (node.available_ram_mb - task.resources.ram_mb)
            / node.available_ram_mb
        ) / 2.0

        prox = NodeScoreCalculator._nodes_proximity_score(
            task_requester_ip, node.ip_address
        )
        return alpha * res + beta * prox
