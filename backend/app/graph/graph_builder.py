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

            # Classes
            for cls in file.analysis.classes:

                class_id = f"{file.path}:{cls}"

                graph.nodes.append(
                    GraphNode(
                        id=class_id,
                        type=NodeType.CLASS,
                        name=cls
                    )
                )

                graph.edges.append(
                    GraphEdge(
                        source=file_node.id,
                        target=class_id,
                        relation=EdgeType.CONTAINS
                    )
                )

            # Functions
            for func in file.analysis.functions:

                func_id = f"{file.path}:{func}"

                graph.nodes.append(
                    GraphNode(
                        id=func_id,
                        type=NodeType.FUNCTION,
                        name=func
                    )
                )

                graph.edges.append(
                    GraphEdge(
                        source=file_node.id,
                        target=func_id,
                        relation=EdgeType.CONTAINS
                    )
                )

            # Methods
            for method in file.analysis.methods:

                method_id = f"{file.path}:{method}"

                graph.nodes.append(
                    GraphNode(
                        id=method_id,
                        type=NodeType.METHOD,
                        name=method
                    )
                )

                graph.edges.append(
                    GraphEdge(
                        source=file_node.id,
                        target=method_id,
                        relation=EdgeType.CONTAINS
                    )
                )

            # Imports
            for imp in file.analysis.imports:

                module_id = f"module:{imp}"

                graph.nodes.append(
                    GraphNode(
                        id=module_id,
                        type=NodeType.MODULE,
                        name=imp
                    )
                )

                graph.edges.append(
                    GraphEdge(
                        source=file_node.id,
                        target=module_id,
                        relation=EdgeType.IMPORTS
                    )
                )

        project.graph = graph

        return project