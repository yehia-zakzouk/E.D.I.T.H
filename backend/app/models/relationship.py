from dataclasses import dataclass


@dataclass
class Relationship:
    source: str
    target: str
    kind: str = "import"
