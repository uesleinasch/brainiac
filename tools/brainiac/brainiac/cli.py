from pathlib import Path

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

    # Phase 5: events + top activations
    from brainiac.core.activation import activation_batch
    event_count = conn.execute("SELECT COUNT(*) FROM accesses").fetchone()[0]
    click.echo(f"events recorded: {event_count}")

    if event_count > 0:
        active_ids = [r[0] for r in conn.execute(
            "SELECT id FROM notes WHERE archived = 0"
        ).fetchall()]
        acts = activation_batch(conn, active_ids)
        ranked = sorted(
            [(nid, a) for nid, a in acts.items() if a != float("-inf")],
            key=lambda x: x[1], reverse=True,
        )[:5]
        if ranked:
            click.echo("top 5 by activation:")
            for nid, a in ranked:
                click.echo(f"  {nid}: {a:.2f}")


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
@click.option("--limit", type=int, default=20, help="Max notes to review in one session.")
def review(limit: int) -> None:
    """Interactive SM-2 review session. Grade 0-5, 's' to skip, 'q' to quit."""
    from brainiac.core.sm2 import grade_review, review_queue

    root = find_root()
    conn = connect(index_db_path(root))
    queue = review_queue(conn)

    if not queue:
        click.echo("Review queue is empty. Nothing due today.")
        return

    click.echo(f"{len(queue)} note(s) due. Showing up to {limit}.")
    reviewed = 0
    skipped = 0
    for item in queue[:limit]:
        click.echo("")
        click.echo(f"📝 {item['id']} ({item['type']})")
        click.echo(
            f"   reps={item['reps']} ease={item['ease']:.2f} "
            f"interval={item['interval']}d overdue={item['days_overdue']}d"
        )
        choice = click.prompt(
            "   Grade [0-5], s to skip, q to quit",
            default="s",
        )
        if choice == "q":
            break
        if choice == "s":
            skipped += 1
            continue
        try:
            g = int(choice)
        except ValueError:
            click.echo("   invalid input, skipping")
            skipped += 1
            continue
        if not 0 <= g <= 5:
            click.echo("   grade out of range, skipping")
            skipped += 1
            continue
        new_sm2 = grade_review(conn, root, item["id"], q=g)
        click.echo(
            f"   Reviewed → ease={new_sm2.ease:.2f} "
            f"interval={new_sm2.interval}d next={new_sm2.next_review.isoformat()}"
        )
        reviewed += 1

    click.echo("")
    click.echo(f"Session complete. Reviewed: {reviewed}, skipped: {skipped}")


@main.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def classify(path: Path) -> None:
    """Suggest a type (episodic/semantic/working) for an existing .md note."""
    from brainiac.core.classifier import classify as classify_body
    from brainiac.core.note import parse_note

    fm, body = parse_note(path)
    suggested, confidence = classify_body(body, tags=fm.tags)

    click.echo(f"file: {path}")
    click.echo(f"current type: {fm.type}")
    if suggested is None:
        click.echo("suggested: ambiguous (consider asking the user or refining the body)")
    else:
        click.echo(f"suggested: {suggested} (confidence: {confidence:.2f})")


@main.command()
@click.argument("note_id")
def inspect(note_id: str) -> None:
    """Show the 3 cognitive axes + access history for a note."""
    from brainiac.core.activation import access_history, activation

    root = find_root()
    conn = connect(index_db_path(root))
    row = conn.execute(
        "SELECT type, access_count, strength, last_access, sm2_json, archived "
        "FROM notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    if row is None:
        raise click.ClickException(f"Note not found: {note_id}")

    note_type, access_count, strength, last_access, sm2_json, archived = row
    act = activation(conn, note_id)

    click.echo(f"id: {note_id}")
    click.echo(f"type: {note_type}")
    click.echo(f"archived: {bool(archived)}")
    click.echo("")
    click.echo("Eixos cognitivos:")
    click.echo(f"  retention:  {strength:.3f} (Ebbinghaus)")
    if act == float("-inf"):
        click.echo("  activation: no trace yet (no accesses)")
    else:
        click.echo(f"  activation: {act:.3f} (ACT-R)")
    if sm2_json:
        import json
        sm2 = json.loads(sm2_json)
        click.echo(
            f"  sm2:        ease={sm2['ease']} interval={sm2['interval']} "
            f"reps={sm2['reps']} next={sm2['next_review']}"
        )
    else:
        click.echo("  sm2:        not enrolled")
    click.echo("")
    click.echo(f"access_count: {access_count}")
    click.echo(f"last_access: {last_access}")
    click.echo("")
    history = access_history(conn, note_id, limit=10)
    if history:
        click.echo(f"Últimos {len(history)} acessos:")
        for h in history:
            click.echo(f"  {h['ts']}  {h['source']}  (w={h['weight']})")
    else:
        click.echo("Sem acessos registrados.")


@main.command()
def mcp() -> None:
    """Start the MCP stdio server."""
    from brainiac.mcp_server import run_server
    run_server()
