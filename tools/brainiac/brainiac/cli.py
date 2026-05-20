import click

from brainiac.core.index import connect, reindex_all
from brainiac.core.paths import find_root, index_db_path


@click.group()
def main() -> None:
    """brainiac — cognitive memory CLI"""


@main.command()
def reindex() -> None:
    """Rebuild the SQLite index from .md files."""
    root = find_root()
    conn = connect(index_db_path(root))
    n = reindex_all(conn, root)
    click.echo(f"reindexed {n} note(s) from {root}")


@main.command()
def stats() -> None:
    """Print counters by type and totals."""
    root = find_root()
    conn = connect(index_db_path(root))

    total = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    by_type = conn.execute(
        "SELECT type, COUNT(*) FROM notes GROUP BY type ORDER BY type"
    ).fetchall()
    link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

    click.echo(f"root: {root}")
    click.echo(f"total notes: {total}")
    for t, c in by_type:
        click.echo(f"  {t}: {c}")
    click.echo(f"links: {link_count}")


@main.command()
def mcp() -> None:
    """Start the MCP stdio server."""
    from brainiac.mcp_server import run_server
    run_server()
