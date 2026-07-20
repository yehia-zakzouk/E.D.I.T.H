import ast

from app.services.analyzer.base import BaseAnalyzer
from app.models.file_analysis import FileAnalysis
from app.models.symbol import Symbol, CallRelation, InheritanceRelation


class PythonAnalyzer(ast.NodeVisitor, BaseAnalyzer):

    def __init__(self):
        self.analysis = FileAnalysis()
        self.current_class = None
        self.current_function = None
        self.scope_stack: list[str] = []

    def extract(self, source: str) -> FileAnalysis:
        self.analysis = FileAnalysis()
        self.current_class = None
        self.current_function = None
        self.scope_stack = []

        tree = ast.parse(source)
        self.analysis.module_docstring = ast.get_docstring(tree)
        self.visit(tree)

        return self.analysis

    # -------------------------
    # Module
    # -------------------------

    def visit_Module(self, node):
        self.generic_visit(node)

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
            if module:
                self.analysis.imports.append(f"{module}.{alias.name}")
            else:
                self.analysis.imports.append(alias.name)

        self.generic_visit(node)

    # -------------------------
    # Classes
    # -------------------------

    def visit_ClassDef(self, node):
        self.analysis.classes.append(node.name)
        self._collect_decorators(node)
        self._collect_bases(node)

        symbol = Symbol(
            name=node.name,
            qualified_name=node.name,
            kind="class",
            line=node.lineno,
            docstring=ast.get_docstring(node),
            decorators=[self._expr_to_name(deco) for deco in node.decorator_list if self._expr_to_name(deco)],
            bases=[self._expr_to_name(base) for base in node.bases if self._expr_to_name(base)],
        )
        self.analysis.symbols.append(symbol)

        if self._is_dataclass(node):
            self.analysis.dataclasses.append(node.name)

        if self._is_enum(node):
            self.analysis.enums.append(node.name)

        previous_class = self.current_class
        self.current_class = node.name
        self.scope_stack.append(node.name)

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_class = previous_class

    # -------------------------
    # Functions / Methods
    # -------------------------

    def visit_FunctionDef(self, node):
        self._handle_function(node, async_def=False)

    def visit_AsyncFunctionDef(self, node):
        self._handle_function(node, async_def=True)

    def _handle_function(self, node, async_def: bool):
        self._collect_decorators(node)
        self._collect_type_hints(node)

        qualified_name = node.name
        if self.current_class:
            qualified_name = f"{self.current_class}.{node.name}"

        if self.current_class:
            self.analysis.methods.append(qualified_name)
        else:
            self.analysis.functions.append(node.name)

        self.analysis.async_functions.append(qualified_name if async_def else qualified_name)

        symbol = Symbol(
            name=node.name,
            qualified_name=qualified_name,
            kind="async_method" if async_def and self.current_class else "async_function" if async_def else "method" if self.current_class else "function",
            line=node.lineno,
            docstring=ast.get_docstring(node),
            decorators=[self._expr_to_name(deco) for deco in node.decorator_list if self._expr_to_name(deco)],
            type_hints=self._collect_type_hints(node, return_list=True),
            parent=self.current_class,
        )
        self.analysis.symbols.append(symbol)

        previous_function = self.current_function
        self.current_function = qualified_name
        self.scope_stack.append(qualified_name)

        self.generic_visit(node)

        self.scope_stack.pop()
        self.current_function = previous_function

    def visit_AnnAssign(self, node):
        if node.annotation is not None:
            target_name = self._get_target_name(node.target)
            annotation = self._annotation_to_string(node.annotation)
            self.analysis.type_hints.append(f"{target_name}: {annotation}")

        self.generic_visit(node)

    def visit_arg(self, node):
        if node.annotation is not None:
            annotation = self._annotation_to_string(node.annotation)
            self.analysis.type_hints.append(f"{node.arg}: {annotation}")

    def visit_Call(self, node):
        if self.current_function:
            callee = self._expr_to_name(node.func)
            if callee:
                self.analysis.calls.append(
                    CallRelation(
                        caller=self.current_function,
                        callee=callee,
                        line=node.lineno,
                    )
                )
        self.generic_visit(node)

    # -------------------------
    # Helpers
    # -------------------------

    def _collect_decorators(self, node):
        for decorator in getattr(node, "decorator_list", []):
            name = self._expr_to_name(decorator)
            if name:
                self.analysis.decorators.append(name)

    def _collect_type_hints(self, node, return_list: bool = False):
        hints = []

        for argument in getattr(node.args, "args", []):
            if argument.annotation is not None:
                annotation = self._annotation_to_string(argument.annotation)
                hints.append(f"{argument.arg}: {annotation}")
                if not return_list:
                    self.analysis.type_hints.append(f"{argument.arg}: {annotation}")

        for argument in getattr(node.args, "kwonlyargs", []):
            if argument.annotation is not None:
                annotation = self._annotation_to_string(argument.annotation)
                hints.append(f"{argument.arg}: {annotation}")
                if not return_list:
                    self.analysis.type_hints.append(f"{argument.arg}: {annotation}")

        if getattr(node.args, "vararg", None) is not None and node.args.vararg.annotation is not None:
            annotation = self._annotation_to_string(node.args.vararg.annotation)
            hint = f"*{node.args.vararg.arg}: {annotation}"
            hints.append(hint)
            if not return_list:
                self.analysis.type_hints.append(hint)

        if getattr(node.args, "kwarg", None) is not None and node.args.kwarg.annotation is not None:
            annotation = self._annotation_to_string(node.args.kwarg.annotation)
            hint = f"**{node.args.kwarg.arg}: {annotation}"
            hints.append(hint)
            if not return_list:
                self.analysis.type_hints.append(hint)

        if getattr(node, "returns", None) is not None:
            annotation = self._annotation_to_string(node.returns)
            hint = f"return: {annotation}"
            hints.append(hint)
            if not return_list:
                self.analysis.type_hints.append(hint)

        return hints

    def _collect_bases(self, node):
        for base in node.bases:
            base_name = self._expr_to_name(base)
            if base_name:
                self.analysis.inheritance_relations.append(
                    InheritanceRelation(
                        child=node.name,
                        parent=base_name,
                        line=node.lineno,
                    )
                )

    def _expr_to_name(self, node):
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Attribute):
            value = self._expr_to_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr

        if isinstance(node, ast.Call):
            return self._expr_to_name(node.func)

        try:
            return ast.unparse(node)
        except Exception:
            return ""

    def _annotation_to_string(self, node):
        try:
            return ast.unparse(node)
        except Exception:
            return ""

    def _get_target_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return self._expr_to_name(node)
        try:
            return ast.unparse(node)
        except Exception:
            return ""

    def _is_dataclass(self, node):
        return any(
            decorator == "dataclass" or decorator.endswith(".dataclass")
            for decorator in (self._expr_to_name(deco) for deco in node.decorator_list)
        )

    def _is_enum(self, node):
        return any(
            base == "Enum" or base.endswith(".Enum")
            for base in (self._expr_to_name(base) for base in node.bases)
        )
