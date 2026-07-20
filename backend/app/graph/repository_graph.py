from pydantic import BaseModel, Field

from app.graph.nodes import GraphNode
from app.graph.edges import GraphEdge


class RepositoryGraph(BaseModel):

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)