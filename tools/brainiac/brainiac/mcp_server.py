"""MCP server exposing brainiac tools via stdio.

Tools (7): add_note, recall, get_note, link, list_recent, consolidate_check, forget
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
) -> dict:
    """Create a new note. Body should start with '# title'."""
    root = find_root()
    fm = new_note(note_id=note_id, note_type=note_type, tags=tags or [])

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


# --- MCP server plumbing ---

server = Server("brainiac")


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="add_note",
            description="Create a new brainiac note with frontmatter and index it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "note_id": {"type": "string", "description": "Format: YYYY-MM-DD-slug"},
                    "note_type": {"type": "string", "enum": ["episodic", "semantic", "working"]},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
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
    ]


_DISPATCH = {
    "add_note": tool_add_note,
    "recall": tool_recall,
    "get_note": tool_get_note,
    "link": tool_link,
    "list_recent": tool_list_recent,
    "consolidate_check": tool_consolidate_check,
    "forget": tool_forget,
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
