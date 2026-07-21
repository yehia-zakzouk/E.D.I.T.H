from enum import Enum

from pydantic import BaseModel


class EdgeType(str, Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    USES = "uses"
    CREATES = "creates"
    REFERENCES = "references"


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: EdgeType