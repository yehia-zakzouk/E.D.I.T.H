import ast

from app.services.analyzer.base import BaseAnalyzer
from app.models.file_analysis import FileAnalysis

class PythonAnalyzer(ast.NodeVisitor):

    def __init__(self):
        self.analysis = FileAnalysis()
        self.current_class = None

    def extract(self, source: str) -> FileAnalysis:
        # Reset state for every file
        self.analysis = FileAnalysis()
        self.current_class = None

        tree = ast.parse(source)
        self.visit(tree)

        return self.analysis

    # -------------------------
    # Imports
    # -------------------------

    def visit_Import(self, node):

        for alias in node.names:
            self.analysis.imports.append(alias.name)

        self.generic_visit(node)

    def visit_ImportFrom(self, node):

        module = node.module or ""

        for alias in node.names:
            self.analysis.imports.append(f"{module}.{alias.name}")

        self.generic_visit(node)

    # -------------------------
    # Classes
    # -------------------------

    def visit_ClassDef(self, node):

        self.analysis.classes.append(node.name)

        previous_class = self.current_class
        self.current_class = node.name

        self.generic_visit(node)

        self.current_class = previous_class

    # -------------------------
    # Functions / Methods
    # -------------------------

    def visit_FunctionDef(self, node):

        if self.current_class:
            self.analysis.methods.append(
                f"{self.current_class}.{node.name}"
            )
        else:
            self.analysis.functions.append(node.name)

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)