from enum import StrEnum, auto


class TaskTypeEnum(StrEnum):
    FUNCTION_WITH_FILES = auto()
    FUNCTION_WITH_INPUT = auto()
    WORKFLOW = auto()
    MAP = auto()
    SHUFFLE_SORT = auto()
    REDUCE = auto()
    COMBINER = auto()


class ComputeStatusEnum(StrEnum):
    CANCELLED = auto()
    RECEIVED = auto()
    PROCESSED = auto()
    CODE_SAFE = auto()
    INPUT_SAFE = auto()
    SCHEDULED = auto()
    EXECUTING = auto()
    FINISHED = auto()
    FAILED = auto()
