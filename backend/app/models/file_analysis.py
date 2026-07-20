from dataclasses import dataclass, field

@dataclass
class FileAnalysis:

    imports: list[str] = field(default_factory=list)

    classes: list[str] = field(default_factory=list)

    functions: list[str] = field(default_factory=list)

    methods: list[str] = field(default_factory=list)

    todos: list[str] = field(default_factory=list)

    complexity: int = 0
    