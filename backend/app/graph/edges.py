from enum import Enum

from pydantic import BaseModel


class EdgeType(str, Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    REFERENCES = "references"


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: EdgeType