#!/usr/bin/env python
"""Test script to validate dashboard setup."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def test_imports():
    """Test that all dashboard modules can be imported."""
    print("Testing imports...")
    try:
        from talk_show_analyzer.dashboard import utils
        print("✓ utils module imported")

        from talk_show_analyzer.db import get_session
        print("✓ db module imported")

        from talk_show_analyzer.models import (
            Episode,
            Station,
            Segment,
            Topic,
            Guest,
            GuestAppearance,
            SentimentResult,
        )
        print("✓ models imported")

        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False


def test_database_connection():
    """Test database connection."""
    print("\nTesting database connection...")
    try:
        from talk_show_analyzer.db import get_session
        from talk_show_analyzer.models import Station

        with get_session() as session:
            count = session.query(Station).count()
            print(f"✓ Database connected ({count} stations found)")
            return True
    except Exception as e:
        print(f"✗ Database error: {e}")
        print("  Make sure DATABASE_URL is set in .env and PostgreSQL is running")
        return False


def test_query_functions():
    """Test dashboard query functions."""
    print("\nTesting query functions...")
    try:
        from talk_show_analyzer.dashboard.utils import (
            get_stations,
            get_episodes,
            get_sentiment_stats,
        )

        # Disable caching for testing
        import streamlit as st
        st.session_state["_cache"] = {}

        stations = get_stations()
        print(f"✓ get_stations() returned {len(stations)} stations")

        episodes = get_episodes(days=7)
        print(f"✓ get_episodes() returned {len(episodes)} episodes")

        sentiment = get_sentiment_stats(days=7)
        print(f"✓ get_sentiment_stats() returned data")

        return True
    except Exception as e:
        print(f"✗ Query error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_streamlit_pages():
    """Verify all page files exist."""
    print("\nVerifying dashboard pages...")
    base_path = Path(__file__).parent / "src/talk_show_analyzer/dashboard"

    pages = {
        "app.py": "Main app",
        "pages/overview.py": "Overview page",
        "pages/episodes.py": "Episodes page",
        "pages/guests.py": "Guest leaderboard page",
        "pages/topics.py": "Topics page",
        "pages/sentiment.py": "Sentiment analysis page",
        "utils.py": "Utility functions",
    }

    all_exist = True
    for page, description in pages.items():
        path = base_path / page
        if path.exists():
            print(f"✓ {description} exists ({page})")
        else:
            print(f"✗ {description} missing ({page})")
            all_exist = False

    return all_exist


def main():
    """Run all tests."""
    print("=" * 60)
    print("Israeli Talk Show Analyzer - Dashboard Test")
    print("=" * 60)

    tests = [
        ("Imports", test_imports),
        ("Database Connection", test_database_connection),
        ("Query Functions", test_query_functions),
        ("Dashboard Pages", test_streamlit_pages),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ {name} test failed: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Dashboard is ready to run:")
        print("   python run_dashboard.py")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
