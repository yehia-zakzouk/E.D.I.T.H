from app.graph.repository_graph import RepositoryGraph
from app.graph.nodes import GraphNode, NodeType
from app.graph.edges import GraphEdge, EdgeType


class GraphBuilder:

    def build(self, project):

        graph = RepositoryGraph()

        for file in project.indexed_files:

            file_node = GraphNode(
                id=str(file.path),
                type=NodeType.FILE,
                name=file.path.name
            )

            graph.nodes.append(file_node)

            if file.analysis is None:
                continue

            existing_nodes = {node.id for node in graph.nodes}

            # Symbol nodes
            for symbol in file.analysis.symbols:
                symbol_id = f"{file.path}:{symbol.qualified_name}"
                node_type = NodeType.METHOD if symbol.kind in ("method", "async_method") else (
                    NodeType.CLASS if symbol.kind == "class" else NodeType.FUNCTION
                )

                if symbol_id not in existing_nodes:
                    graph.nodes.append(
                        GraphNode(
                            id=symbol_id,
                            type=node_type,
                            name=symbol.qualified_name,
                            lineno=symbol.line,
                            docstring=symbol.docstring,
                        )
                    )
                    existing_nodes.add(symbol_id)

                graph.edges.append(
                    GraphEdge(
                        source=file_node.id,
                        target=symbol_id,
                        relation=EdgeType.CONTAINS
                    )
                )

                graph.edges.append(
                    GraphEdge(
                        source=file_node.id,
                        target=symbol_id,
                        relation=EdgeType.CREATES
                    )
                )

            # Call graph edges
            for call in file.analysis.calls:
                caller_id = f"{file.path}:{call.caller}"
                callee_id = f"call:{call.callee}"

                if callee_id not in existing_nodes:
                    graph.nodes.append(
                        GraphNode(
                            id=callee_id,
                            type=NodeType.FUNCTION,
                            name=call.callee,
                        )
                    )
                    existing_nodes.add(callee_id)

                graph.edges.append(
                    GraphEdge(
                        source=caller_id,
                        target=callee_id,
                        relation=EdgeType.CALLS
                    )
                )

                graph.edges.append(
                    GraphEdge(
                        source=caller_id,
                        target=callee_id,
                        relation=EdgeType.USES
                    )
                )

            # Inheritance edges
            for inheritance in file.analysis.inheritance_relations:
                child_id = f"{file.path}:{inheritance.child}"
                parent_id = f"inherit:{inheritance.parent}"

                if parent_id not in existing_nodes:
                    graph.nodes.append(
                        GraphNode(
                            id=parent_id,
                            type=NodeType.CLASS,
                            name=inheritance.parent,
                        )
                    )
                    existing_nodes.add(parent_id)

                graph.edges.append(
                    GraphEdge(
                        source=child_id,
                        target=parent_id,
                        relation=EdgeType.INHERITS
                    )
                )

            # Imports
            for imp in file.analysis.imports:
                module_id = f"module:{imp}"

                if module_id not in existing_nodes:
                    graph.nodes.append(
                        GraphNode(
                            id=module_id,
                            type=NodeType.MODULE,
                            name=imp
                        )
                    )
                    existing_nodes.add(module_id)

                graph.edges.append(
                    GraphEdge(
                        source=file_node.id,
                        target=module_id,
                        relation=EdgeType.IMPORTS
                    )
                )

                graph.edges.append(
                    GraphEdge(
                        source=file_node.id,
                        target=module_id,
                        relation=EdgeType.USES
                    )
                )

        project.graph = graph

        return project