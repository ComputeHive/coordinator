from core.services.heartbeat_service import HeartbeatService


class ComputeService:
    def __init__(self, heartbeat_service: HeartbeatService):
        self.heartbeat_service = heartbeat_service
