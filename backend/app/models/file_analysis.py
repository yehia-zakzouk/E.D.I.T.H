from dataclasses import asdict, dataclass, field
from typing import Optional

from app.models.symbol import Symbol, CallRelation, InheritanceRelation


@dataclass
class FileAnalysis:

    module_docstring: Optional[str] = None

    imports: list[str] = field(default_factory=list)

    classes: list[str] = field(default_factory=list)

    functions: list[str] = field(default_factory=list)

    methods: list[str] = field(default_factory=list)

    decorators: list[str] = field(default_factory=list)

    type_hints: list[str] = field(default_factory=list)

    async_functions: list[str] = field(default_factory=list)

    dataclasses: list[str] = field(default_factory=list)

    enums: list[str] = field(default_factory=list)

    todos: list[str] = field(default_factory=list)

    symbols: list[Symbol] = field(default_factory=list)

    calls: list[CallRelation] = field(default_factory=list)

    inheritance_relations: list[InheritanceRelation] = field(default_factory=list)

    complexity: int = 0

    def to_dict(self) -> dict:
        result = asdict(self)
        return result

    @staticmethod
    def from_dict(data: dict) -> "FileAnalysis":
        analysis = FileAnalysis(
            module_docstring=data.get("module_docstring"),
            imports=data.get("imports", []),
            classes=data.get("classes", []),
            functions=data.get("functions", []),
            methods=data.get("methods", []),
            decorators=data.get("decorators", []),
            type_hints=data.get("type_hints", []),
            async_functions=data.get("async_functions", []),
            dataclasses=data.get("dataclasses", []),
            enums=data.get("enums", []),
            todos=data.get("todos", []),
            complexity=data.get("complexity", 0),
        )

        analysis.symbols = [Symbol(**symbol_data) for symbol_data in data.get("symbols", [])]
        analysis.calls = [CallRelation(**call_data) for call_data in data.get("calls", [])]
        analysis.inheritance_relations = [
            InheritanceRelation(**inheritance_data)
            for inheritance_data in data.get("inheritance_relations", [])
        ]

        return analysis
