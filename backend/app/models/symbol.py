from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Parameter:
    name: str
    annotation: Optional[str] = None
    default: Optional[str] = None
    kind: Optional[str] = None


@dataclass
class Symbol:
    name: str
    qualified_name: str
    kind: str
    file: str
    line: int
    end_line: Optional[int] = None
    column: Optional[int] = None
    parent: Optional[str] = None
    docstring: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    return_type: Optional[str] = None
    type_hints: list[str] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)


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
