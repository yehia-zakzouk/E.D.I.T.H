from dataclasses import dataclass


@dataclass
class Dependency:
    source: str
    target: str
    kind: str = "import"