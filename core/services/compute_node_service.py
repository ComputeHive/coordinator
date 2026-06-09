import dataclasses

from core.domain.exceptions import AuthenticationError, ConflictError
from core.domain.models import ComputeNodeCreateRequest
from core.services.auth_service import AuthService
from core.services.heartbeat_service import HeartbeatService
from infrastructure.database.mongo_repositories import (
    MongoComputeNodeRepository,
)


class ComputeNodeService:
    def __init__(
        self,
        heartbeat_service: HeartbeatService,
        auth_service: AuthService,
        db_repo: MongoComputeNodeRepository,
    ):
        self.heartbeat_service = heartbeat_service
        self._auth = auth_service
        self._db_repo = db_repo

    def create_compute_node(self, compute_node: ComputeNodeCreateRequest):
        compute_node_dict = dataclasses.asdict(compute_node)
        if self.verify_exists(compute_node_dict["username"]):
            raise ConflictError("Username already exists")
        compute_node_dict["password"] = self._auth.hash_password(
            compute_node.password
        )
        edited_compute_node = ComputeNodeCreateRequest(**compute_node_dict)
        self._db_repo.create(edited_compute_node)

    def authenticate_compute_node(self, username: str, password: str):

        compute_node = self._db_repo.find_by_username(username)
        if not compute_node or not self._auth.verify_password(
            password, compute_node.password
        ):
            raise AuthenticationError("Wrong username or password.")
        return self._auth.issue_token(username)

    def verify_exists(self, username: str) -> bool:
        return self._db_repo.find_by_username(username) is not None
