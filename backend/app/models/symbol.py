from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Symbol:
    name: str
    qualified_name: str
    kind: str
    line: int
    docstring: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    type_hints: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    parent: Optional[str] = None


@dataclass
class CallRelation:
    caller: str
    callee: str
    line: int


@dataclass
class InheritanceRelation:
    child: str
    parent: str
    line: int
