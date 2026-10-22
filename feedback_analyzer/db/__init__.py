"""db package — SQLite connection, schema, and repository."""

from feedback_analyzer.db.connection import (
    connection_scope,
    get_connection,
    init_db,
)
from feedback_analyzer.db.repository import (
    DatabaseError,
    DuplicateTicketError,
    get_analysis,
    get_status_counts,
    get_ticket,
    insert_analysis,
    insert_ticket,
    list_all_tickets_with_results,
    list_processed_tickets,
    ticket_exists,
)

__all__ = [
    "DatabaseError",
    "DuplicateTicketError",
    "connection_scope",
    "get_analysis",
    "get_connection",
    "get_status_counts",
    "get_ticket",
    "init_db",
    "insert_analysis",
    "insert_ticket",
    "list_all_tickets_with_results",
    "list_processed_tickets",
    "ticket_exists",
]
