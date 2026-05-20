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
    active, archived = reindex_all(conn, root)
    msg = f"reindexed {active} active note(s) from {root}"
    if archived:
        msg += f" ({archived} archived)"
    click.echo(msg)


@main.command()
def stats() -> None:
    """Print counters by type and totals."""
    root = find_root()
    conn = connect(index_db_path(root))

    total = conn.execute("SELECT COUNT(*) FROM notes WHERE archived = 0").fetchone()[0]
    by_type = conn.execute(
        "SELECT type, COUNT(*) FROM notes WHERE archived = 0 GROUP BY type ORDER BY type"
    ).fetchall()
    link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    archived_count = conn.execute("SELECT COUNT(*) FROM notes WHERE archived = 1").fetchone()[0]

    click.echo(f"root: {root}")
    click.echo(f"total notes: {total}")
    for t, c in by_type:
        click.echo(f"  {t}: {c}")
    click.echo(f"links: {link_count}")
    click.echo(f"archived: {archived_count}")


@main.command()
@click.option("--dry-run", is_flag=True, help="Show what would be archived without archiving.")
def decay(dry_run: bool) -> None:
    """Run Ebbinghaus decay: update strength, archive notes below threshold."""
    from brainiac.core.decay import run_decay

    root = find_root()
    conn = connect(index_db_path(root))
    stats = run_decay(conn, root, dry_run=dry_run)
    prefix = "[dry-run] " if dry_run else ""
    click.echo(
        f"{prefix}decay complete — "
        f"checked: {stats['checked']}, "
        f"updated: {stats['updated']}, "
        f"archived: {stats['archived']}"
    )


@main.command()
@click.option("--auto", is_flag=True, help="Promote all candidates to suggested type without prompting.")
def consolidate(auto: bool) -> None:
    """Check and promote working notes to long/semantic memory."""
    from brainiac.core.consolidate import consolidation_candidates, promote_note

    root = find_root()
    conn = connect(index_db_path(root))
    candidates = consolidation_candidates(conn)

    if not candidates:
        click.echo("No candidates for promotion.")
        return

    click.echo(f"{len(candidates)} candidate(s) for promotion:")
    promoted = 0
    for c in candidates:
        click.echo(
            f"  {c['id']} → {c['suggested_type']} "
            f"(accesses: {c['access_count']}, fan_in: {c['fan_in']})"
        )
        if auto:
            promote_note(conn, root, c["id"], c["suggested_type"])
            promoted += 1
        else:
            choice = click.prompt(
                "  Promote as [semantic/episodic/skip]",
                default="skip",
            )
            if choice in ("semantic", "episodic"):
                promote_note(conn, root, c["id"], choice)
                promoted += 1

    click.echo(f"Promoted {promoted} note(s).")


@main.command()
def mcp() -> None:
    """Start the MCP stdio server."""
    from brainiac.mcp_server import run_server
    run_server()
