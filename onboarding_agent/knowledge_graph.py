"""A simple file-backed knowledge graph for storing codebase entities and relationships.

Entities are things like files, functions, classes, and modules.
Relationships connect them: "file contains function", "file imports module", etc.

The graph persists to a JSON file so it survives server restarts.
"""

import json
from pathlib import Path


class KnowledgeGraph:
    """In-memory knowledge graph with JSON file persistence.

    Each entity has:
        - id: unique identifier (e.g., file path or "filepath::function_name")
        - type: "file", "function", "class", "module"
        - name: human-readable name
        - metadata: dict of extra info (language, size, etc.)

    Each relationship has:
        - source: entity id
        - target: entity id
        - type: "contains", "imports", "calls", etc.
    """

    def __init__(self, storage_path: str | None = None):
        self.entities: dict[str, dict] = {}
        self.relationships: list[dict] = []
        self.storage_path = Path(storage_path) if storage_path else None

        if self.storage_path and self.storage_path.exists():
            self._load()

    def add_entity(self, entity_id: str, entity_type: str, name: str, metadata: dict | None = None) -> None:
        """Add or update an entity in the graph."""
        self.entities[entity_id] = {
            "id": entity_id,
            "type": entity_type,
            "name": name,
            "metadata": metadata or {},
        }

    def add_relationship(self, source: str, target: str, rel_type: str) -> None:
        """Add a relationship between two entities. Skips duplicates."""
        rel = {"source": source, "target": target, "type": rel_type}
        if rel not in self.relationships:
            self.relationships.append(rel)

    def get_entity(self, entity_id: str) -> dict | None:
        """Look up a single entity by id."""
        return self.entities.get(entity_id)

    def find_entities(self, entity_type: str | None = None, name_contains: str | None = None) -> list[dict]:
        """Search entities by type and/or name substring."""
        results = list(self.entities.values())
        if entity_type:
            results = [e for e in results if e["type"] == entity_type]
        if name_contains:
            query = name_contains.lower()
            results = [e for e in results if query in e["name"].lower()]
        return results

    def find_relationships(
        self,
        source: str | None = None,
        target: str | None = None,
        rel_type: str | None = None,
    ) -> list[dict]:
        """Search relationships by source, target, and/or type."""
        results = self.relationships
        if source:
            results = [r for r in results if r["source"] == source]
        if target:
            results = [r for r in results if r["target"] == target]
        if rel_type:
            results = [r for r in results if r["type"] == rel_type]
        return results

    def get_neighbors(self, entity_id: str) -> dict:
        """Find all entities directly connected to the given entity."""
        outgoing = self.find_relationships(source=entity_id)
        incoming = self.find_relationships(target=entity_id)

        connected_ids = set()
        for r in outgoing:
            connected_ids.add(r["target"])
        for r in incoming:
            connected_ids.add(r["source"])

        return {
            "entity": self.get_entity(entity_id),
            "outgoing": outgoing,
            "incoming": incoming,
            "neighbors": [self.entities[eid] for eid in connected_ids if eid in self.entities],
        }

    def clear(self) -> None:
        """Wipe the graph."""
        self.entities.clear()
        self.relationships.clear()

    def save(self) -> None:
        """Persist the graph to disk as JSON."""
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entities": self.entities, "relationships": self.relationships}
        self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load graph from disk."""
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self.entities = data.get("entities", {})
            self.relationships = data.get("relationships", [])
        except (json.JSONDecodeError, KeyError):
            self.entities = {}
            self.relationships = []

    def stats(self) -> dict:
        """Return summary stats about the graph."""
        type_counts: dict[str, int] = {}
        for e in self.entities.values():
            t = e["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        rel_type_counts: dict[str, int] = {}
        for r in self.relationships:
            t = r["type"]
            rel_type_counts[t] = rel_type_counts.get(t, 0) + 1

        return {
            "total_entities": len(self.entities),
            "total_relationships": len(self.relationships),
            "entities_by_type": type_counts,
            "relationships_by_type": rel_type_counts,
        }
