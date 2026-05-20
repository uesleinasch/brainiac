"""MCP server exposing brainiac tools via stdio.

Tools (12): add_note, recall, get_note, link, list_recent,
            consolidate_check, forget,
            review_queue, grade_review, start_review,
            working_status,
            inspect_note
"""

import asyncio
import json
from datetime import datetime, timezone

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from brainiac.core.index import (
    add_link,
    connect,
    get_note,
    index_note,
    list_recent,
)
from brainiac.core.note import new_note, write_note
from brainiac.core.paths import find_root, index_db_path, note_path


# --- Pure tool functions (testable without MCP plumbing) ---

def tool_add_note(
    note_id: str,
    note_type: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    study: bool = False,
) -> dict:
    """Create a new note. Body should start with '# title'.

    If note_type='working' and shortMemory is full per config, returns a
    structured error with eviction candidates instead of creating the note.
    If study=True, enrolls in SM-2.
    """
    root = find_root()

    if note_type == "working":
        from brainiac.core.config import load_config
        from brainiac.core.working_memory import (
            WorkingMemoryFullError,
            check_working_capacity,
        )
        conn = connect(index_db_path(root))
        try:
            check_working_capacity(conn, load_config(root))
        except WorkingMemoryFullError as exc:
            return {
                "error": str(exc),
                "count": exc.count,
                "limit": exc.limit,
                "suggestion": exc.candidates,
            }

    fm = new_note(note_id=note_id, note_type=note_type, tags=tags or [])

    if study:
        from brainiac.core.sm2 import start_sm2
        fm.sm2 = start_sm2()

    # ensure body starts with a title line
    body_with_title = body if body.lstrip().startswith("#") else f"# {title}\n\n{body}"

    path = note_path(root, note_id, note_type)
    write_note(path, fm, body_with_title)

    conn = connect(index_db_path(root))
    rel = path.relative_to(root)
    index_note(conn, fm, body_with_title, str(rel))

    return {"id": note_id, "path": str(rel), "type": note_type}


def tool_recall(query: str, k: int = 5) -> list[dict]:
    """Recall associativo (semantic + 1-hop) com fallback para FTS5."""
    from brainiac.core.index import recall
    root = find_root()
    conn = connect(index_db_path(root))
    return recall(conn, query, k=k)


def tool_get_note(note_id: str) -> dict:
    """Read note; increments access_count."""
    root = find_root()
    conn = connect(index_db_path(root))
    return get_note(conn, root, note_id)


def tool_link(src: str, dst: str) -> dict:
    """Add explicit link src→dst."""
    root = find_root()
    conn = connect(index_db_path(root))
    add_link(conn, root, src, dst)
    return {"src": src, "dst": dst, "kind": "explicit"}


def tool_list_recent(limit: int = 10) -> list[dict]:
    """Last N notes ordered by last_access desc."""
    root = find_root()
    conn = connect(index_db_path(root))
    return list_recent(conn, limit=limit)


def tool_consolidate_check(window_days: int = 7) -> list[dict]:
    """Return working notes qualified for promotion."""
    from brainiac.core.consolidate import consolidation_candidates
    root = find_root()
    conn = connect(index_db_path(root))
    return consolidation_candidates(conn, window_days=window_days)


def tool_forget(note_id: str) -> dict:
    """Archive a note immediately (manual forget)."""
    from brainiac.core.decay import archive_note
    root = find_root()
    conn = connect(index_db_path(root))
    new_path = archive_note(conn, root, note_id)
    return {"id": note_id, "archived_path": new_path, "action": "archived"}


def tool_review_queue() -> list[dict]:
    """Return notes whose next_review <= today, ordered by urgency then ease."""
    from brainiac.core.sm2 import review_queue
    root = find_root()
    conn = connect(index_db_path(root))
    return review_queue(conn)


def tool_grade_review(note_id: str, grade: int) -> dict:
    """Apply a grade (0-5) to a review. Returns new SM2 state."""
    from brainiac.core.sm2 import grade_review
    root = find_root()
    conn = connect(index_db_path(root))
    sm2 = grade_review(conn, root, note_id, q=grade)
    return {
        "id": note_id,
        "ease": sm2.ease,
        "interval": sm2.interval,
        "reps": sm2.reps,
        "next_review": sm2.next_review.isoformat(),
    }


def tool_start_review(note_id: str) -> dict:
    """Enroll an existing note in spaced repetition."""
    from brainiac.core.sm2 import start_review
    root = find_root()
    conn = connect(index_db_path(root))
    sm2 = start_review(conn, root, note_id)
    return {
        "id": note_id,
        "ease": sm2.ease,
        "interval": sm2.interval,
        "reps": sm2.reps,
        "next_review": sm2.next_review.isoformat(),
    }


def tool_working_status() -> dict:
    """Snapshot of shortMemory occupancy + eviction candidates if full."""
    from brainiac.core.config import load_config
    from brainiac.core.working_memory import working_status
    root = find_root()
    conn = connect(index_db_path(root))
    return working_status(conn, load_config(root))


def tool_inspect_note(note_id: str) -> dict:
    """Snapshot dos 3 eixos cognitivos (retention/activation/sm2) + audit trail."""
    import json
    from brainiac.core.activation import access_history, activation
    root = find_root()
    conn = connect(index_db_path(root))
    row = conn.execute(
        "SELECT type, access_count, strength, last_access, sm2_json, archived "
        "FROM notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Note not found: {note_id}")
    return {
        "id": note_id,
        "type": row[0],
        "access_count": row[1],
        "strength": row[2],
        "last_access": row[3],
        "sm2": json.loads(row[4]) if row[4] else None,
        "archived": bool(row[5]),
        "activation": activation(conn, note_id),
        "recent_accesses": access_history(conn, note_id, limit=10),
    }


# --- MCP server plumbing ---

server = Server("brainiac")


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="add_note",
            description="Create a new brainiac note with frontmatter and index it. study=true enrolls in SM-2 spaced repetition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "Format: YYYY-MM-DD-slug"},
                    "note_type": {"type": "string", "enum": ["episodic", "semantic", "working"]},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "study": {"type": "boolean", "default": False},
                },
                "required": ["note_id", "note_type", "title", "body"],
            },
        ),
        Tool(
            name="recall",
            description=(
                "Recall associativo: top-k semântico (embeddings 384-dim) + expansão 1-hop "
                "no grafo. Cada item retorna origin ∈ {semantic, explicit, implicit, both, fts}. "
                "FTS5 fica como fallback se o modelo de embeddings falhar."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_note",
            description="Read a note. Increments access_count and last_access.",
            inputSchema={
                "type": "object",
                "properties": {"note_id": {"type": "string"}},
                "required": ["note_id"],
            },
        ),
        Tool(
            name="link",
            description="Add explicit link from src note to dst note.",
            inputSchema={
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                },
                "required": ["src", "dst"],
            },
        ),
        Tool(
            name="list_recent",
            description="Last N notes by last_access.",
            inputSchema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 10}},
            },
        ),
        Tool(
            name="consolidate_check",
            description=(
                "Lista notas working prontas para promoção (access_count≥3, "
                "acessadas recentemente, com pelo menos 1 link recebido). "
                "Retorna candidatos com suggested_type."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "window_days": {"type": "integer", "default": 7},
                },
            },
        ),
        Tool(
            name="forget",
            description=(
                "Arquiva uma nota agora, removendo-a da memória ativa. "
                "Reversível: nota vai para memoryTransfer/archive/."
            ),
            inputSchema={
                "type": "object",
                "properties": {"note_id": {"type": "string"}},
                "required": ["note_id"],
            },
        ),
        Tool(
            name="review_queue",
            description=(
                "Lista notas inscritas em SM-2 vencidas hoje. "
                "Ordenadas por urgência (mais atrasada primeiro), tiebreak por ease menor."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="grade_review",
            description=(
                "Aplica grade 0-5 a uma revisão SM-2. "
                "0-2 = falha (reseta interval=1); 3-5 = sucesso (avança). "
                "Também incrementa access_count/last_access."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "string"},
                    "grade": {"type": "integer", "minimum": 0, "maximum": 5},
                },
                "required": ["note_id", "grade"],
            },
        ),
        Tool(
            name="start_review",
            description="Inscreve uma nota existente em revisão espaçada (cria bloco sm2).",
            inputSchema={
                "type": "object",
                "properties": {"note_id": {"type": "string"}},
                "required": ["note_id"],
            },
        ),
        Tool(
            name="working_status",
            description=(
                "Snapshot do estado da shortMemory: ocupação atual, limite configurado, "
                "se está cheia, e candidatos a promover/descartar quando cheia."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="inspect_note",
            description=(
                "Snapshot dos 3 eixos cognitivos de uma nota: retention (Ebbinghaus), "
                "activation (ACT-R), sm2 (SuperMemo-2), além dos últimos 10 acessos "
                "registrados com source e weight."
            ),
            inputSchema={
                "type": "object",
                "properties": {"note_id": {"type": "string"}},
                "required": ["note_id"],
            },
        ),
    ]


_DISPATCH = {
    "add_note": tool_add_note,
    "recall": tool_recall,
    "get_note": tool_get_note,
    "link": tool_link,
    "list_recent": tool_list_recent,
    "consolidate_check": tool_consolidate_check,
    "forget": tool_forget,
    "review_queue": tool_review_queue,
    "grade_review": tool_grade_review,
    "start_review": tool_start_review,
    "working_status": tool_working_status,
    "inspect_note": tool_inspect_note,
}


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
    fn = _DISPATCH.get(name)
    if fn is None:
        raise ValueError(f"Unknown tool: {name}")
    try:
        result = fn(**(arguments or {}))
    except Exception as exc:
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]
    return [TextContent(type="text", text=json.dumps(result, default=str))]


async def _run() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def run_server() -> None:
    """Sync entry point for `brainiac mcp`."""
    asyncio.run(_run())
