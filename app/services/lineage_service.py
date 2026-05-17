from collections import deque

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.lineage import LineageEdge


class LineageService:
    """Сервис по работе со связями lineage."""

    @classmethod
    def model(cls) -> LineageEdge:
        """Возвращаем модель."""
        return LineageEdge()

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        from_entity_type: str,
        from_entity_id: int,
        to_entity_type: str,
        to_entity_id: int,
        relation_type: str,
    ) -> LineageEdge:
        """Создаем связь lineage."""
        edge = LineageEdge(
            from_entity_type=from_entity_type,
            from_entity_id=from_entity_id,
            to_entity_type=to_entity_type,
            to_entity_id=to_entity_id,
            relation_type=relation_type,
        )
        db.add(edge)
        return edge

    @classmethod
    def filter_all(
        cls,
        db: Session,
        where_clause: list | None = None,
    ) -> list[LineageEdge]:
        """Список активных связей lineage."""
        statement = select(LineageEdge).where(LineageEdge.deleted_at.is_(None)).order_by(LineageEdge.id)

        if where_clause:
            statement = statement.where(*where_clause)

        return db.scalars(statement).all()

    @classmethod
    def get_graph(
        cls,
        db: Session,
        entity_type: str,
        entity_id: int,
        mode: str = "full",
    ) -> tuple[list[tuple[str, int]], list[LineageEdge]]:
        """Получаем lineage-граф для сущности.

        full: все связанные узлы; direct: только ближайшие связи;
        upstream: объекты, от которых зависит выбранная сущность;
        downstream: объекты, которые зависят от выбранной сущности.
        """
        if mode not in {"full", "direct", "upstream", "downstream"}:
            mode = "full"

        queue: deque[tuple[str, int]] = deque([(entity_type, entity_id)])
        visited_nodes = {(entity_type, entity_id)}
        visited_edges: set[int] = set()
        edges: list[LineageEdge] = []

        while queue:
            current_type, current_id = queue.popleft()

            if mode == "upstream":
                edge_filter = and_(
                    LineageEdge.to_entity_type == current_type,
                    LineageEdge.to_entity_id == current_id,
                )
            elif mode == "downstream":
                edge_filter = and_(
                    LineageEdge.from_entity_type == current_type,
                    LineageEdge.from_entity_id == current_id,
                )
            else:
                edge_filter = or_(
                    and_(
                        LineageEdge.from_entity_type == current_type,
                        LineageEdge.from_entity_id == current_id,
                    ),
                    and_(
                        LineageEdge.to_entity_type == current_type,
                        LineageEdge.to_entity_id == current_id,
                    ),
                )

            result = cls.filter_all(db=db, where_clause=[edge_filter])

            for edge in result:
                if edge.id in visited_edges:
                    continue

                visited_edges.add(edge.id)
                edges.append(edge)

                if mode == "upstream":
                    neighbors = [(edge.from_entity_type, edge.from_entity_id)]
                elif mode == "downstream":
                    neighbors = [(edge.to_entity_type, edge.to_entity_id)]
                else:
                    neighbors = [
                        (edge.from_entity_type, edge.from_entity_id),
                        (edge.to_entity_type, edge.to_entity_id),
                    ]

                for neighbor in neighbors:
                    if neighbor not in visited_nodes:
                        visited_nodes.add(neighbor)
                        if mode != "direct":
                            queue.append(neighbor)

        nodes = [
            (node_type, node_id)
            for node_type, node_id in sorted(visited_nodes, key=lambda item: (item[0], item[1]))
        ]
        return nodes, edges

    @classmethod
    def remove_related_by_entity(cls, db: Session, entity_type: str, entity_id: int) -> None:
        """Мягко удаляем все связи, связанные с сущностью."""
        edges = cls.filter_all(
            db=db,
            where_clause=[
                or_(
                    and_(
                        LineageEdge.from_entity_type == entity_type,
                        LineageEdge.from_entity_id == entity_id,
                    ),
                    and_(
                        LineageEdge.to_entity_type == entity_type,
                        LineageEdge.to_entity_id == entity_id,
                    ),
                )
            ],
        )

        for edge in edges:
            edge.mark_deleted()


def add_lineage_edge(
    db: Session,
    *,
    from_entity_type: str,
    from_entity_id: int,
    to_entity_type: str,
    to_entity_id: int,
    relation_type: str,
) -> LineageEdge:
    """Совместимость со старым функциональным стилем."""
    return LineageService.create(
        db=db,
        from_entity_type=from_entity_type,
        from_entity_id=from_entity_id,
        to_entity_type=to_entity_type,
        to_entity_id=to_entity_id,
        relation_type=relation_type,
    )


def get_lineage_graph(db: Session, entity_type: str, entity_id: int, mode: str = "full") -> tuple[list[tuple[str, int]], list[LineageEdge]]:
    """Совместимость со старым функциональным стилем."""
    return LineageService.get_graph(db=db, entity_type=entity_type, entity_id=entity_id, mode=mode)


def soft_delete_related_edges(db: Session, entity_type: str, entity_id: int) -> None:
    """Совместимость со старым функциональным стилем."""
    LineageService.remove_related_by_entity(db=db, entity_type=entity_type, entity_id=entity_id)
