from pathlib import Path

from app.models.project import Project
from app.database.database import DatabaseManager
print(Project.model_fields.keys())
from app.services.scanner import RepositoryScanner
from app.services.detector import ProjectDetector
from app.services.indexer import RepositoryIndexer
from app.services.knowledge_extractor import KnowledgeExtractor



def print_analysis(file):
    print("=" * 80)
    print(f"📄 {file.path.name}")
    print("=" * 80)

    print(f"📍 Path  : {file.path}")
    print(f"📏 Size  : {file.size} bytes")
    print(f"📄 Lines : {file.lines}")
    print(f"🔑 Hash  : {file.hash[:16]}...")

    print("\n📦 Imports")
    if file.analysis.imports:
        for imp in file.analysis.imports:
            print(f"   • {imp}")
    else:
        print("   None")

    print("\n🏛 Classes")
    if file.analysis.classes:
        for cls in file.analysis.classes:
            print(f"   • {cls}")
    else:
        print("   None")

    print("\n⚙ Functions")
    if file.analysis.functions:
        for func in file.analysis.functions:
            print(f"   • {func}")
    else:
        print("   None")

    print("\n🔧 Methods")
    if file.analysis.methods:
        for method in file.analysis.methods:
            print(f"   • {method}")
    else:
        print("   None")

    print()


def main():
    # Change this path to any repository you want EDITH to analyze
    project_path = Path(r"D:\E.D.I.T.H")

    project = Project(root=project_path)

    scanner = RepositoryScanner()
    detector = ProjectDetector()
    indexer = RepositoryIndexer()
    analyzer = KnowledgeExtractor()

    print("🔍 Scanning repository...")
    project.files = scanner.scan(str(project.root))

    print("🧠 Detecting technologies...")
    project = detector.detect(project)

    print("📚 Indexing files...")
    project = indexer.index(project)

    print("🧩 Extracting knowledge...")
    project = analyzer.analyze(project)

    print("\n========== PROJECT SUMMARY ==========")
    print(f"Languages      : {project.languages}")
    print(f"Frameworks     : {project.frameworks}")
    print(f"Build System   : {project.build_system}")
    print(f"Docker         : {project.docker}")
    print(f"Git            : {project.git}")
    print(f"Files Found    : {len(project.files)}")
    print(f"Indexed Files  : {len(project.indexed_files)}")

    print("\n========== FILE ANALYSIS ==========\n")

    for file in project.indexed_files:
        print_analysis(file)
    print("\n")
    print("=" * 80)
    print("DEPENDENCY GRAPH")
    print("=" * 80)
    for dep in project.dependencies:

     print(f"{dep.source}  ─────►  {dep.target}")
    print("\n")
    print("=" * 80)
    print("REPOSITORY GRAPH")
    print("=" * 80)

    print(f"\nNodes: {len(project.graph.nodes)}")
    print(f"Edges: {len(project.graph.edges)}")

    for node in project.graph.nodes[:15]:
     print(f"{node.type.value:<10} {node.name}")

    print()

    for edge in project.graph.edges[:20]:
     print(f"{edge.source} --{edge.relation.value}--> {edge.target}") 
db = DatabaseManager("edith.db")
db.initialize()

if __name__ == "__main__":
    main()