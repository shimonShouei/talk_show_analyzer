"""DB round-trip tests for PartORM and the orchestrator's _persist_parts helper.

Uses an isolated in-memory SQLite engine so no .env / persistent DB is required.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from talk_show_analyzer.analysis.structural_segmenter import Part, PartType
from talk_show_analyzer.models import Base, Episode, PartORM, Station


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _episode(session: Session) -> int:
    station = Station(name="103fm", stream_url="http://example/stream")
    session.add(station)
    session.commit()
    ep = Episode(
        station_id=station.id,
        recorded_at=datetime(2024, 1, 1, 7, 30),
        duration=3600.0,
        audio_path="/tmp/x.mp3",
        language="he",
        word_count=0,
        raw_text="",
        status="pending",
    )
    session.add(ep)
    session.commit()
    return ep.id


def test_part_orm_roundtrip(session):
    ep_id = _episode(session)
    row = PartORM(
        episode_id=ep_id,
        idx=0,
        type=PartType.INTERVIEW.value,
        start_seconds=10.0,
        end_seconds=400.0,
        host_labels=["H0"],
        guest_labels=["G0", "G1"],
        unknown_labels=[],
    )
    session.add(row)
    session.commit()

    fetched = session.query(PartORM).filter_by(episode_id=ep_id).one()
    assert fetched.type == "interview"
    assert fetched.start_seconds == 10.0
    assert fetched.end_seconds == 400.0
    assert fetched.host_labels == ["H0"]
    assert fetched.guest_labels == ["G0", "G1"]
    assert fetched.duration == 390.0


def test_persist_parts_writes_then_replaces(session, monkeypatch):
    """_persist_parts should replace any pre-existing parts for the same episode."""
    from talk_show_analyzer.pipeline import orchestrator as orch_mod

    ep_id = _episode(session)

    # Patch get_session to yield our test session inside the helper.
    from contextlib import contextmanager

    @contextmanager
    def fake_session():
        yield session

    monkeypatch.setattr(orch_mod, "get_session", fake_session)

    orch = orch_mod.PipelineOrchestrator.__new__(orch_mod.PipelineOrchestrator)

    parts_v1 = [
        Part(
            type=PartType.INTERVIEW,
            start=0,
            end=300,
            host_labels={"H"},
            guest_labels={"G"},
        ),
        Part(
            type=PartType.HOST_TALK,
            start=300,
            end=400,
            host_labels={"H"},
        ),
    ]
    orch._persist_parts(ep_id, parts_v1)
    rows = session.query(PartORM).filter_by(episode_id=ep_id).order_by(PartORM.idx).all()
    assert [r.type for r in rows] == ["interview", "host_talk"]
    assert rows[0].guest_labels == ["G"]
    assert rows[1].host_labels == ["H"]

    # Replace with a single new part — old rows should be gone.
    parts_v2 = [
        Part(
            type=PartType.INTERVIEW,
            start=0,
            end=500,
            host_labels={"H"},
            guest_labels={"G2"},
        )
    ]
    orch._persist_parts(ep_id, parts_v2)
    rows = session.query(PartORM).filter_by(episode_id=ep_id).all()
    assert len(rows) == 1
    assert rows[0].guest_labels == ["G2"]
    assert rows[0].idx == 0
