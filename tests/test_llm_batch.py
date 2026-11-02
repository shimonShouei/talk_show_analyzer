"""run_batched: rounds, replay, and sync fallback (no network)."""
from types import SimpleNamespace

import pytest

from talk_show_analyzer.analysis import llm_batch
from talk_show_analyzer.analysis.llm_batch import run_batched


def _msg(text):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return SimpleNamespace(model="claude-haiku-4-5", usage=usage,
                           content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    def __init__(self, fail_batch=False):
        self.sync_calls = 0
        self.batches_submitted = 0
        self._store = {}
        self.fail_batch = fail_batch
        outer = self

        class Batches:
            def create(self, requests):
                if outer.fail_batch:
                    raise RuntimeError("boom")
                outer.batches_submitted += 1
                bid = f"b{outer.batches_submitted}"
                outer._store[bid] = requests
                return SimpleNamespace(id=bid, processing_status="ended")

            def retrieve(self, bid):
                return SimpleNamespace(id=bid, processing_status="ended")

            def results(self, bid):
                for r in outer._store[bid]:
                    yield SimpleNamespace(
                        custom_id=r["custom_id"],
                        result=SimpleNamespace(type="succeeded",
                                               message=_msg("B:" + r["params"]["messages"][0]["content"])),
                    )

        def create(**params):
            outer.sync_calls += 1
            return _msg("S:" + params["messages"][0]["content"])

        self.messages = SimpleNamespace(create=create, batches=Batches())


class Analyzer:
    def __init__(self, client):
        self.client = client

    def ask(self, q):
        r = self.client.messages.create(model="m", max_tokens=10,
                                        messages=[{"role": "user", "content": q}])
        return r.content[0].text


def test_two_calls_per_item_use_two_batch_rounds(monkeypatch):
    monkeypatch.setattr(llm_batch.settings, "llm_batch_poll_seconds", 0)
    c = FakeClient()
    a, b = Analyzer(c), Analyzer(c)
    out = run_batched([a, b], lambda x: (a.ask(x), b.ask(x + "!")), ["q1", "q2"])
    assert out == [("B:q1", "B:q1!"), ("B:q2", "B:q2!")]
    assert c.batches_submitted == 2 and c.sync_calls == 0
    assert a.client is c and b.client is c  # clients restored


def test_batch_failure_falls_back_to_sync(monkeypatch):
    c = FakeClient(fail_batch=True)
    a = Analyzer(c)
    out = run_batched(a, a.ask, ["x", "y"])
    assert out == ["S:x", "S:y"] and c.sync_calls == 2


def test_exception_handlers_do_not_swallow_deferral(monkeypatch):
    monkeypatch.setattr(llm_batch.settings, "llm_batch_poll_seconds", 0)
    c = FakeClient()
    a = Analyzer(c)

    def guarded(x):
        try:
            return a.ask(x)
        except Exception:  # analyzers catch Exception; _Deferred must pass through
            return "swallowed"

    assert run_batched(a, guarded, ["z"]) == ["B:z"]
