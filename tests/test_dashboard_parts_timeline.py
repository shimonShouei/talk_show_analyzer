"""Integration tests for the Parts Timeline dashboard data-loading functions.

Uses an in-memory SQLite DB — no .env required.
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from talk_show_analyzer.models import (
    Base,
    Episode,
    HateSpeechIncidentORM,
    MergedTopic,
    PartORM,
    Station,
)


# ─────────────────────────────── fixtures ────────────────────────────────────

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


@pytest.fixture
def db_url():
    return "sqlite:///:memory:"


@pytest.fixture
def populated_db(tmp_path):
    """Return a sqlite URL (file-based so helpers can open their own sessions)."""
    db_file = tmp_path / "test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()

    station = Station(name="galatz", stream_url="http://example/stream")
    s.add(station)
    s.commit()

    ep = Episode(
        station_id=station.id,
        recorded_at=datetime(2025, 1, 15, 8, 0),
        duration=1800.0,
        audio_path="/tmp/ep.mp3",
        language="he",
        word_count=500,
        raw_text="test",
        status="analyzed",
    )
    s.add(ep)
    s.commit()
    ep_id = ep.id  # capture before session closes

    part0 = PartORM(
        episode_id=ep.id,
        idx=0,
        type="host_talk",
        start_seconds=0.0,
        end_seconds=300.0,
        host_labels=["H0"],
        guest_labels=[],
        unknown_labels=[],
    )
    part1 = PartORM(
        episode_id=ep.id,
        idx=1,
        type="interview",
        start_seconds=300.0,
        end_seconds=900.0,
        host_labels=["H0"],
        guest_labels=["G0", "G1"],
        unknown_labels=[],
    )
    s.add_all([part0, part1])
    s.commit()

    topic = MergedTopic(
        episode_id=ep.id,
        topic_id="t0",
        merged_title_he="נושא ראשי",
        merged_title_en="Main Topic",
        category="politics",
        thematic_flow_he="",
        time_spans=[[200.0, 800.0]],
        chunk_ids=[],
    )
    s.add(topic)
    s.commit()

    incident = HateSpeechIncidentORM(
        merged_topic_id=topic.id,
        speaker_label="G0",
        level="insulting",
        target="opponent",
        phrase_he="ביטוי",
        context_he="הקשר",
        rationale_en="reason",
    )
    s.add(incident)
    s.commit()
    s.close()

    return url, ep_id


# ─────────────────────────────── tests ───────────────────────────────────────

def test_load_all_episodes_returns_list(populated_db):
    url, ep_id = populated_db
    from talk_show_analyzer.dashboard.pages.parts_timeline import load_all_episodes

    episodes = load_all_episodes(db_url=url)
    assert len(episodes) == 1
    e = episodes[0]
    assert e["id"] == ep_id
    assert e["station"] == "galatz"
    assert "label" in e
    assert "galatz" in e["label"]


def test_load_parts_returns_correct_count(populated_db):
    url, ep_id = populated_db
    from talk_show_analyzer.dashboard.pages.parts_timeline import load_parts

    parts = load_parts(ep_id, db_url=url)
    assert len(parts) == 2


def test_load_parts_topic_overlap(populated_db):
    """The topic spans [200, 800] should overlap both parts."""
    url, ep_id = populated_db
    from talk_show_analyzer.dashboard.pages.parts_timeline import load_parts

    parts = load_parts(ep_id, db_url=url)
    # part0: [0, 300] overlaps [200, 800]
    # part1: [300, 900] overlaps [200, 800]
    assert parts[0]["n_topics"] == 1
    assert parts[1]["n_topics"] == 1


def test_load_parts_fields(populated_db):
    url, ep_id = populated_db
    from talk_show_analyzer.dashboard.pages.parts_timeline import load_parts

    parts = load_parts(ep_id, db_url=url)
    p1 = next(p for p in parts if p["type"] == "interview")
    assert "H0" in p1["host_labels"]
    assert "G0" in p1["guest_labels"]
    assert p1["duration"] == pytest.approx(600.0)


def test_load_hate_heatmap_shape(populated_db):
    url, ep_id = populated_db
    from talk_show_analyzer.dashboard.pages.parts_timeline import load_hate_heatmap

    df, speakers, topic_labels = load_hate_heatmap(ep_id, db_url=url)
    assert not df.empty
    # speakers include H0, G0, G1 (from parts) plus G0 from incidents
    assert "G0" in speakers
    assert df.shape[0] == len(speakers)
    assert df.shape[1] == 1  # one merged topic


def test_load_hate_heatmap_max_level(populated_db):
    """G0 had 'insulting' level=3; all others should be 0."""
    url, ep_id = populated_db
    from talk_show_analyzer.dashboard.pages.parts_timeline import load_hate_heatmap

    df, speakers, topic_labels = load_hate_heatmap(ep_id, db_url=url)
    g0_row = df.loc["G0"]
    assert int(g0_row.iloc[0]) == 3  # insulting → 3

    h0_row = df.loc["H0"]
    assert int(h0_row.iloc[0]) == 0


def test_empty_episode_no_parts(populated_db):
    """load_parts on a non-existent episode_id returns empty list."""
    url, _ = populated_db
    from talk_show_analyzer.dashboard.pages.parts_timeline import load_parts

    parts = load_parts(999999, db_url=url)
    assert parts == []
