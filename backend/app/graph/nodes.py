from enum import Enum

from pydantic import BaseModel


class NodeType(str, Enum):
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    MODULE = "module"


class GraphNode(BaseModel):
    id: str
    type: NodeType
    name: str