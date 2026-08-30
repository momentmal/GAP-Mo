import datetime
import functools
import itertools
import logging
import threading
from collections.abc import Iterable

import pandas as pd
import sqlalchemy as sa
from tqdm import tqdm

from ...core.datamodel import DB, UiConfig
from ...core.tile_visits import get_tile_history_df, get_visited_tiles
from ...core.tiles import adjacent_to
from .model import (
    ClusterHistoryEvent,
    ClusterHistoryStatus,
    ClusterMembership,
    ClusterSizeHistory,
    ClusterTileActivation,
    ExplorerSquare,
    InaccessibleTile,
    SquareHistory,
)

logger = logging.getLogger(__name__)

_history_rebuild_lock = threading.Lock()


class TileEvolutionState:
    """Accumulator for the two evolution plot series of one zoom level."""

    def __init__(self) -> None:
        self.cluster_evolution = pd.DataFrame()
        self.square_start = 0
        self.cluster_start = 0
        self.max_square_size = 0
        self.visited_tiles: set[tuple[int, int]] = set()
        self.square_evolution = pd.DataFrame()
        self.square_x: int | None = None
        self.square_y: int | None = None
        # Tiles that are present from the origin of time, currently the
        # inaccessible tiles that count toward cluster and square.
        self.seed_tiles: set[tuple[int, int]] = set()


class ClusterReplayState:
    def __init__(self) -> None:
        self.visited_tiles: set[tuple[int, int]] = set()
        self.neighbor_counts: dict[tuple[int, int], int] = {}
        self.cluster_tiles: set[tuple[int, int]] = set()
        self.parents: dict[tuple[int, int], tuple[int, int]] = {}
        self.component_sizes: dict[tuple[int, int], int] = {}
        self.max_cluster_size = 0


def _find_root(
    parents: dict[tuple[int, int], tuple[int, int]], tile: tuple[int, int]
) -> tuple[int, int]:
    root = tile
    while parents[root] != root:
        root = parents[root]
    while parents[tile] != tile:
        parent = parents[tile]
        parents[tile] = root
        tile = parent
    return root


def _union_roots(
    state: ClusterReplayState,
    left: tuple[int, int],
    right: tuple[int, int],
) -> None:
    left_root = _find_root(state.parents, left)
    right_root = _find_root(state.parents, right)
    if left_root == right_root:
        return
    if state.component_sizes[left_root] < state.component_sizes[right_root]:
        left_root, right_root = right_root, left_root
    state.parents[right_root] = left_root
    state.component_sizes[left_root] += state.component_sizes[right_root]
    del state.component_sizes[right_root]
    if state.component_sizes[left_root] > state.max_cluster_size:
        state.max_cluster_size = state.component_sizes[left_root]


def _activate_cluster_tile(state: ClusterReplayState, tile: tuple[int, int]) -> None:
    if tile in state.cluster_tiles:
        return
    state.cluster_tiles.add(tile)
    state.parents[tile] = tile
    state.component_sizes[tile] = 1
    if state.max_cluster_size < 1:
        state.max_cluster_size = 1
    for other in adjacent_to(tile):
        if other in state.cluster_tiles:
            _union_roots(state, tile, other)


def apply_cluster_history_event(
    state: ClusterReplayState, tile: tuple[int, int]
) -> int | None:
    if tile in state.visited_tiles:
        return None
    previous_max = state.max_cluster_size
    state.visited_tiles.add(tile)
    state.neighbor_counts.setdefault(tile, 0)

    for other in adjacent_to(tile):
        if other in state.visited_tiles:
            state.neighbor_counts[tile] += 1
            state.neighbor_counts[other] = state.neighbor_counts.get(other, 0) + 1
            if state.neighbor_counts[other] == 4:
                _activate_cluster_tile(state, other)

    if state.neighbor_counts[tile] == 4:
        _activate_cluster_tile(state, tile)

    if state.max_cluster_size > previous_max:
        return state.max_cluster_size
    return None


def compute_current_cluster_state(
    tiles: Iterable[tuple[int, int]],
) -> ClusterReplayState:
    """Cluster state of a tile set, independent of when the tiles were visited.

    ``apply_cluster_history_event`` is order-independent, so replaying a set in
    arbitrary order yields the same clusters as replaying the real history.
    """
    state = ClusterReplayState()
    for tile in tiles:
        apply_cluster_history_event(state, tile)
    return state


def compute_max_square(
    tiles: Iterable[tuple[int, int]],
) -> tuple[int | None, int | None, int]:
    """Largest square of covered tiles, as ``(square_x, square_y, size)``.

    Uses the maximal-square recurrence: ``dp[x, y]`` is the side length of the
    largest covered square whose maximum corner is ``(x, y)``. Sorting by
    ``(x, y)`` guarantees that the three predecessors are known already.
    """
    dp: dict[tuple[int, int], int] = {}
    best_size = 0
    best_x: int | None = None
    best_y: int | None = None
    for x, y in sorted(tiles):
        size = 1 + min(
            dp.get((x - 1, y), 0),
            dp.get((x, y - 1), 0),
            dp.get((x - 1, y - 1), 0),
        )
        dp[(x, y)] = size
        if size > best_size:
            best_size = size
            best_x = x - size + 1
            best_y = y - size + 1
    return best_x, best_y, best_size


def get_counted_inaccessible_tiles(zoom: int) -> set[tuple[int, int]]:
    """Inaccessible tiles that count toward the cluster and square, if enabled.

    They never count as visited tiles, so the explored tile counts stay honest;
    they only fill the holes that cluster and square geometry care about.
    """
    from ...core.config import ConfigAccessor

    if not ConfigAccessor().ui().count_inaccessible_in_cluster:
        return set()
    return {
        (row.tile_x, row.tile_y)
        for row in DB.session.execute(
            sa.select(InaccessibleTile.tile_x, InaccessibleTile.tile_y).where(
                InaccessibleTile.zoom == zoom
            )
        )
    }


def get_covered_tiles(zoom: int) -> set[tuple[int, int]]:
    """Tiles that count for cluster and square purposes at a zoom level."""
    return get_visited_tiles(zoom) | get_counted_inaccessible_tiles(zoom)


def compute_current_state_for_zoom(
    zoom: int, tiles: Iterable[tuple[int, int]] | None = None
) -> None:
    """Persist cluster membership and the biggest square for a zoom level.

    This is a pure function of the covered tile set and needs neither the tile
    history nor a replay, so it is cheap enough to run after every change.
    """
    covered = set(get_covered_tiles(zoom) if tiles is None else tiles)
    state = compute_current_cluster_state(covered)
    square_x, square_y, max_square_size = compute_max_square(covered)

    DB.session.query(ClusterMembership).filter(ClusterMembership.zoom == zoom).delete()
    _materialize_cluster_membership(zoom, state)

    DB.session.query(ExplorerSquare).filter(ExplorerSquare.zoom == zoom).delete()
    DB.session.add(
        ExplorerSquare(
            zoom=zoom,
            square_x=square_x,
            square_y=square_y,
            max_square_size=max_square_size,
        )
    )
    DB.session.commit()


def mark_cluster_history_stale(zooms: Iterable[int]) -> None:
    """Flag the stored history of these zoom levels as outdated."""
    for zoom in zooms:
        status = DB.session.get(ClusterHistoryStatus, zoom)
        if status is None:
            DB.session.add(ClusterHistoryStatus(zoom=zoom, stale=True))
        else:
            status.stale = True
    DB.session.commit()


def is_cluster_history_stale(zoom: int) -> bool:
    status = DB.session.get(ClusterHistoryStatus, zoom)
    return status is None or status.stale


def rebuild_cluster_history(zoom: int) -> None:
    """Replay the history of a zoom level and store everything derived from it.

    This is the expensive path: it walks every tile visit in order. Everything
    that only depends on the current tile set lives in
    ``compute_current_state_for_zoom`` and does not come through here.
    """
    tile_history = get_tile_history_df(zoom)
    rebuild_cluster_history_for_zoom(zoom, tile_history)

    state = TileEvolutionState()
    state.seed_tiles = get_counted_inaccessible_tiles(zoom)
    _compute_cluster_evolution(tile_history, state, zoom)
    _compute_square_history(tile_history, state, zoom)
    _persist_evolution_to_db(zoom, state)

    status = DB.session.get(ClusterHistoryStatus, zoom)
    if status is None:
        status = ClusterHistoryStatus(zoom=zoom)
        DB.session.add(status)
    status.stale = False
    status.computed_at = datetime.datetime.now()
    DB.session.commit()


CLUSTER_HISTORY_CLAIM_TIMEOUT = datetime.timedelta(minutes=30)


def _claim_cluster_history_rebuild(zoom: int) -> bool:
    """Try to become the one who rebuilds this zoom level.

    The Explorer page requests its plots in parallel and the server runs several
    worker processes, so without a claim two of them would delete and re-insert
    the same history rows and collide. A single conditional ``UPDATE`` is atomic
    in the database and therefore works across processes, unlike a lock held in
    one of them. A claim that was never released, because the worker died, is
    taken over after a timeout.
    """
    now = datetime.datetime.now()
    result = DB.session.execute(
        sa.update(ClusterHistoryStatus)
        .where(
            ClusterHistoryStatus.zoom == zoom,
            ClusterHistoryStatus.stale,
            sa.or_(
                ClusterHistoryStatus.rebuilding_since.is_(None),
                ClusterHistoryStatus.rebuilding_since
                < now - CLUSTER_HISTORY_CLAIM_TIMEOUT,
            ),
        )
        .values(rebuilding_since=now)
    )
    DB.session.commit()
    return bool(result.rowcount)


def rebuild_cluster_history_if_stale(zoom: int) -> bool:
    """Rebuild the history of a zoom level if needed. Returns whether it ran."""
    # The lock only keeps the threads of this worker from piling up on the
    # claim; the claim itself is what coordinates the worker processes.
    with _history_rebuild_lock:
        if not is_cluster_history_stale(zoom):
            return False
        if DB.session.get(ClusterHistoryStatus, zoom) is None:
            DB.session.add(ClusterHistoryStatus(zoom=zoom, stale=True))
            DB.session.commit()
        if not _claim_cluster_history_rebuild(zoom):
            logger.info(
                f"Another worker is rebuilding the cluster history for {zoom=}."
            )
            return False
        logger.info(f"Rebuilding outdated cluster history for {zoom=}.")
        try:
            rebuild_cluster_history(zoom)
        finally:
            status = DB.session.get(ClusterHistoryStatus, zoom)
            if status is not None:
                status.rebuilding_since = None
                DB.session.commit()
        return True


def compute_tile_evolution(config: UiConfig, zooms: list[int] | None = None) -> None:
    for zoom in config.explorer_zoom_levels if zooms is None else zooms:
        compute_current_state_for_zoom(zoom)
        rebuild_cluster_history(zoom)


def delete_tile_evolution(zoom: int) -> None:
    """Drop all derived cluster and square data of a zoom level."""
    for model in (
        ClusterHistoryEvent,
        ClusterHistoryStatus,
        ClusterMembership,
        ClusterSizeHistory,
        ClusterTileActivation,
        ExplorerSquare,
        SquareHistory,
    ):
        DB.session.query(model).filter(model.zoom == zoom).delete()
    _cluster_state_at_cutoff.cache_clear()
    DB.session.commit()


def _persist_evolution_to_db(zoom: int, state: "TileEvolutionState") -> None:
    """Write the evolution plot series of a zoom to the database.

    The current square lives in ``ExplorerSquare`` and is written by
    ``compute_current_state_for_zoom`` instead, which does not need the history.
    """
    DB.session.query(SquareHistory).filter(SquareHistory.zoom == zoom).delete()
    DB.session.query(ClusterSizeHistory).filter(
        ClusterSizeHistory.zoom == zoom
    ).delete()

    for row in state.square_evolution.itertuples(index=False):
        DB.session.add(
            SquareHistory(
                zoom=zoom,
                time=(row.time.to_pydatetime() if pd.notna(row.time) else None),
                max_square_size=int(row.max_square_size),
                square_x=int(row.square_x),
                square_y=int(row.square_y),
            )
        )

    for row in state.cluster_evolution.itertuples(index=False):
        DB.session.add(
            ClusterSizeHistory(
                zoom=zoom,
                time=(row.time.to_pydatetime() if pd.notna(row.time) else None),
                max_cluster_size=int(row.max_cluster_size),
            )
        )

    DB.session.commit()


def get_explorer_square(zoom: int) -> tuple[int | None, int | None, int]:
    """Return ``(square_x, square_y, max_square_size)`` for a zoom level."""
    row = DB.session.get(ExplorerSquare, zoom)
    if row is None:
        return None, None, 0
    return row.square_x, row.square_y, row.max_square_size


def get_square_history_df(zoom: int) -> pd.DataFrame:
    """Square evolution series for the plot: time, max_square_size, square_x/y."""
    rows = DB.session.execute(
        sa.select(
            SquareHistory.time,
            SquareHistory.max_square_size,
            SquareHistory.square_x,
            SquareHistory.square_y,
        )
        .where(SquareHistory.zoom == zoom)
        .order_by(SquareHistory.id)
    ).all()
    return pd.DataFrame(
        {
            "time": [pd.Timestamp(r.time) if r.time else pd.NaT for r in rows],
            "max_square_size": [r.max_square_size for r in rows],
            "square_x": [r.square_x for r in rows],
            "square_y": [r.square_y for r in rows],
        }
    )


def get_cluster_size_history_df(zoom: int) -> pd.DataFrame:
    """Cluster size evolution series for the plot: time, max_cluster_size."""
    rows = DB.session.execute(
        sa.select(ClusterSizeHistory.time, ClusterSizeHistory.max_cluster_size)
        .where(ClusterSizeHistory.zoom == zoom)
        .order_by(ClusterSizeHistory.id)
    ).all()
    return pd.DataFrame(
        {
            "time": [pd.Timestamp(r.time) if r.time else pd.NaT for r in rows],
            "max_cluster_size": [r.max_cluster_size for r in rows],
        }
    )


def _seeded_replay_state(zoom: int) -> ClusterReplayState:
    """A replay state that already contains the counted inaccessible tiles."""
    state = ClusterReplayState()
    for tile in get_counted_inaccessible_tiles(zoom):
        apply_cluster_history_event(state, tile)
    return state


def rebuild_cluster_history_for_zoom(zoom: int, tile_history: pd.DataFrame) -> None:
    """Replay the tile history once, storing the events and the activations."""
    DB.session.query(ClusterHistoryEvent).filter(
        ClusterHistoryEvent.zoom == zoom
    ).delete()
    DB.session.query(ClusterTileActivation).filter(
        ClusterTileActivation.zoom == zoom
    ).delete()
    _cluster_state_at_cutoff.cache_clear()

    # Inaccessible tiles are counted at the origin of time: they were never
    # reachable, so treating them as present from the start keeps the history
    # consistent with the current state.
    state = _seeded_replay_state(zoom)
    event_batch: list[ClusterHistoryEvent] = []
    # Event index zero marks what already clustered before the first ride.
    activation_batch: list[ClusterTileActivation] = [
        ClusterTileActivation(
            zoom=zoom,
            tile_x=tile[0],
            tile_y=tile[1],
            event_index=0,
            activity_id=None,
            time=None,
        )
        for tile in state.cluster_tiles
    ]

    for event_index, row in enumerate(tile_history.itertuples(index=False), start=1):
        tile = (int(row.tile_x), int(row.tile_y))
        time = row.time.to_pydatetime() if pd.notna(row.time) else None
        event_batch.append(
            ClusterHistoryEvent(
                zoom=zoom,
                event_index=event_index,
                activity_id=int(row.activity_id),
                time=time,
                tile_x=tile[0],
                tile_y=tile[1],
            )
        )

        # Only this tile and its neighbors can reach four neighbors from this
        # event, so those are the only activation candidates.
        candidates = [tile, *adjacent_to(tile)]
        active_before = {other for other in candidates if other in state.cluster_tiles}
        apply_cluster_history_event(state, tile)
        for other in candidates:
            if other in active_before or other not in state.cluster_tiles:
                continue
            activation_batch.append(
                ClusterTileActivation(
                    zoom=zoom,
                    tile_x=other[0],
                    tile_y=other[1],
                    event_index=event_index,
                    activity_id=int(row.activity_id),
                    time=time,
                )
            )

        if len(event_batch) >= 1_000:
            DB.session.add_all(event_batch)
            event_batch = []
        if len(activation_batch) >= 1_000:
            DB.session.add_all(activation_batch)
            activation_batch = []

    DB.session.add_all(event_batch)
    DB.session.add_all(activation_batch)
    DB.session.commit()


def _materialize_cluster_membership(zoom: int, state: ClusterReplayState) -> None:
    """Persist the cluster membership of a state for a zoom level."""
    batch: list[ClusterMembership] = []
    for tile in state.cluster_tiles:
        root = _find_root(state.parents, tile)
        batch.append(
            ClusterMembership(
                zoom=zoom,
                tile_x=tile[0],
                tile_y=tile[1],
                cluster_x=root[0],
                cluster_y=root[1],
            )
        )
        if len(batch) >= 1_000:
            DB.session.add_all(batch)
            batch = []
    if batch:
        DB.session.add_all(batch)


def get_cluster_membership_in_bounds(
    zoom: int, x_min: int, x_max: int, y_min: int, y_max: int
) -> dict[tuple[int, int], tuple[int, int]]:
    """Return ``tile -> representative tile`` for cluster tiles within a viewport."""
    rows = DB.session.execute(
        sa.select(
            ClusterMembership.tile_x,
            ClusterMembership.tile_y,
            ClusterMembership.cluster_x,
            ClusterMembership.cluster_y,
        ).where(
            ClusterMembership.zoom == zoom,
            ClusterMembership.tile_x >= x_min,
            ClusterMembership.tile_x <= x_max,
            ClusterMembership.tile_y >= y_min,
            ClusterMembership.tile_y <= y_max,
        )
    ).all()
    return {(row.tile_x, row.tile_y): (row.cluster_x, row.cluster_y) for row in rows}


def get_cluster_tile_count(zoom: int) -> int:
    """Number of tiles that belong to any cluster at a zoom level."""
    return (
        DB.session.query(ClusterMembership)
        .filter(ClusterMembership.zoom == zoom)
        .count()
    )


def get_max_cluster(zoom: int) -> tuple[tuple[int, int] | None, int]:
    """Return the representative and size of the largest cluster at a zoom level."""
    row = DB.session.execute(
        sa.select(
            ClusterMembership.cluster_x,
            ClusterMembership.cluster_y,
            sa.func.count().label("size"),
        )
        .where(ClusterMembership.zoom == zoom)
        .group_by(ClusterMembership.cluster_x, ClusterMembership.cluster_y)
        .order_by(sa.desc("size"))
        .limit(1)
    ).first()
    if row is None:
        return None, 0
    return (row.cluster_x, row.cluster_y), int(row.size)


def get_cluster_id_for_tile(
    zoom: int, tile_x: int, tile_y: int
) -> tuple[int, int] | None:
    """Return the representative tile of the cluster a tile belongs to, if any."""
    row = DB.session.execute(
        sa.select(ClusterMembership.cluster_x, ClusterMembership.cluster_y).where(
            ClusterMembership.zoom == zoom,
            ClusterMembership.tile_x == tile_x,
            ClusterMembership.tile_y == tile_y,
        )
    ).first()
    if row is None:
        return None
    return (row.cluster_x, row.cluster_y)


def get_cluster_members(
    zoom: int, cluster_x: int, cluster_y: int
) -> list[tuple[int, int]]:
    """Return all member tiles of a cluster identified by its representative."""
    rows = DB.session.execute(
        sa.select(ClusterMembership.tile_x, ClusterMembership.tile_y).where(
            ClusterMembership.zoom == zoom,
            ClusterMembership.cluster_x == cluster_x,
            ClusterMembership.cluster_y == cluster_y,
        )
    ).all()
    return [(row.tile_x, row.tile_y) for row in rows]


def get_biggest_cluster_members(zoom: int) -> list[tuple[int, int]]:
    """Return the member tiles of the largest cluster at a zoom level."""
    representative, _size = get_max_cluster(zoom)
    if representative is None:
        return []
    return get_cluster_members(zoom, representative[0], representative[1])


def get_cluster_history_cutoff_for_activity(
    zoom: int, activity_id: int
) -> tuple[int | None, int | None]:
    first_event = DB.session.scalar(
        sa.select(sa.func.min(ClusterHistoryEvent.event_index)).where(
            ClusterHistoryEvent.zoom == zoom,
            ClusterHistoryEvent.activity_id == activity_id,
        )
    )
    last_event = DB.session.scalar(
        sa.select(sa.func.max(ClusterHistoryEvent.event_index)).where(
            ClusterHistoryEvent.zoom == zoom,
            ClusterHistoryEvent.activity_id == activity_id,
        )
    )
    if first_event is None or last_event is None:
        return None, None
    return int(first_event), int(last_event)


def get_cluster_history_latest_event_index(zoom: int) -> int:
    latest = DB.session.scalar(
        sa.select(sa.func.max(ClusterHistoryEvent.event_index)).where(
            ClusterHistoryEvent.zoom == zoom
        )
    )
    return int(latest or 0)


def get_cluster_tiles_at_cutoff(zoom: int, event_index: int) -> set[tuple[int, int]]:
    """Cluster tiles as of an event index, straight from the activation table.

    Index zero is the state before the first ride, which is not necessarily
    empty: inaccessible tiles counted toward the cluster are seeded there.
    """
    if event_index < 0:
        return set()
    return {
        (row.tile_x, row.tile_y)
        for row in DB.session.execute(
            sa.select(ClusterTileActivation.tile_x, ClusterTileActivation.tile_y).where(
                ClusterTileActivation.zoom == zoom,
                ClusterTileActivation.event_index <= event_index,
            )
        )
    }


@functools.lru_cache(maxsize=2)
def _cluster_state_at_cutoff(zoom: int, event_index: int) -> ClusterReplayState:
    state = _seeded_replay_state(zoom)
    events = DB.session.execute(
        sa.select(ClusterHistoryEvent.tile_x, ClusterHistoryEvent.tile_y)
        .where(
            ClusterHistoryEvent.zoom == zoom,
            ClusterHistoryEvent.event_index <= event_index,
        )
        .order_by(ClusterHistoryEvent.event_index)
    ).all()
    for event in events:
        apply_cluster_history_event(state, (event.tile_x, event.tile_y))
    return state


def get_cluster_state_at_cutoff(zoom: int, event_index: int) -> ClusterReplayState:
    """Full cluster state at an event index, including the cluster identities.

    Only the time slider needs the identities, and it holds one cutoff still
    while the map requests many tile images, so a small cache turns the replay
    into a once-per-slider-position cost.
    """
    if event_index < 0:
        return ClusterReplayState()
    return _cluster_state_at_cutoff(zoom, event_index)


def get_cluster_tiles_gained_by_activity(
    zoom: int, activity_id: int
) -> set[tuple[int, int]]:
    """Tiles that became cluster tiles through the given activity.

    Cluster membership only grows, so an activity can never take tiles away.
    """
    return {
        (row.tile_x, row.tile_y)
        for row in DB.session.execute(
            sa.select(ClusterTileActivation.tile_x, ClusterTileActivation.tile_y).where(
                ClusterTileActivation.zoom == zoom,
                ClusterTileActivation.activity_id == activity_id,
            )
        )
    }


def get_cluster_tile_activations_df(zoom: int) -> pd.DataFrame:
    rows = DB.session.execute(
        sa.select(
            ClusterTileActivation.time,
            ClusterTileActivation.event_index,
            ClusterTileActivation.activity_id,
            ClusterTileActivation.tile_x,
            ClusterTileActivation.tile_y,
        )
        .where(ClusterTileActivation.zoom == zoom)
        .order_by(ClusterTileActivation.event_index)
    ).all()
    return pd.DataFrame(
        {
            "time": [pd.Timestamp(row.time) if row.time else pd.NaT for row in rows],
            "event_index": [row.event_index for row in rows],
            "activity_id": [row.activity_id for row in rows],
            "tile_x": [row.tile_x for row in rows],
            "tile_y": [row.tile_y for row in rows],
        },
        columns=["time", "event_index", "activity_id", "tile_x", "tile_y"],
    )


def _compute_cluster_evolution(
    tiles: pd.DataFrame, s: TileEvolutionState, zoom: int
) -> None:
    """Series of the biggest cluster size over time, via the union-find replay.

    The seed tiles are present from the origin of time, just as in
    ``rebuild_cluster_history_for_zoom``, so the series ends at the same cluster
    size that the current state reports.
    """
    state = compute_current_cluster_state(s.seed_tiles)
    rows = []
    if state.max_cluster_size > 0 and len(tiles) > 0:
        rows.append(
            {
                "time": tiles.iloc[0]["time"],
                "max_cluster_size": state.max_cluster_size,
            }
        )
    for row in tqdm(
        tiles.itertuples(index=False),
        desc=f"Cluster evolution for {zoom=}",
        delay=1,
    ):
        max_cluster_size = apply_cluster_history_event(state, (row.tile_x, row.tile_y))
        if max_cluster_size is not None:
            rows.append({"time": row.time, "max_cluster_size": max_cluster_size})

    s.cluster_evolution = pd.DataFrame(rows)
    s.cluster_start = len(tiles)


def _compute_square_history(
    tiles: pd.DataFrame, s: TileEvolutionState, zoom: int
) -> None:
    """Series of the biggest square size over time.

    Seeded with the same tiles as the cluster evolution, so the series ends at
    the square that the current state reports.
    """
    rows = []
    s.visited_tiles.update(s.seed_tiles)
    s.square_x, s.square_y, s.max_square_size = compute_max_square(s.visited_tiles)
    if s.max_square_size > 0 and len(tiles) > 0:
        rows.append(
            {
                "time": tiles.iloc[0]["time"],
                "max_square_size": s.max_square_size,
                "square_x": s.square_x,
                "square_y": s.square_y,
            }
        )
    for _index, row in tqdm(
        tiles.iterrows(),
        desc=f"Square evolution for {zoom=}",
        delay=1,
    ):
        tile = (row["tile_x"], row["tile_y"])
        if tile in s.visited_tiles:
            continue
        x, y = tile
        s.visited_tiles.add(tile)
        for square_size in itertools.count(s.max_square_size + 1):
            this_tile_size_viable = False
            for x_offset in range(square_size):
                for y_offset in range(square_size):
                    this_offset_viable = True
                    for xx in range(square_size):
                        for yy in range(square_size):
                            if (
                                x + xx - x_offset,
                                y + yy - y_offset,
                            ) not in s.visited_tiles:
                                this_offset_viable = False
                                break
                        if not this_offset_viable:
                            break
                    if this_offset_viable:
                        s.max_square_size = square_size
                        s.square_x = x - x_offset
                        s.square_y = y - y_offset
                        rows.append(
                            {
                                "time": row["time"],
                                "max_square_size": square_size,
                                "square_x": s.square_x,
                                "square_y": s.square_y,
                            }
                        )
                        this_tile_size_viable = True
                        break
                if this_tile_size_viable:
                    break
            if not this_tile_size_viable:
                break

    new_square_history = pd.DataFrame(rows)
    s.square_evolution = pd.concat([s.square_evolution, new_square_history])
    s.square_start = len(tiles)
