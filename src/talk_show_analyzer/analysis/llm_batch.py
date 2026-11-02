"""Run per-item LLM work through the Anthropic Message Batches API (50% off).

Analyzer code stays unchanged: it keeps calling ``self.client.messages.create``.
``run_batched`` swaps the analyzer's ``client`` for a proxy and runs the items
in rounds:

  * record pass - every item is executed until its first *unanswered*
    ``messages.create`` call; the request params are recorded and the item is
    aborted with ``_Deferred`` (a BaseException, so analyzers' ``except
    Exception`` handlers don't swallow it);
  * all recorded requests are submitted as one batch and polled until done;
  * the next pass replays answered calls from the batch results, so items
    progress to their next call (e.g. a validation retry, or a second
    analyzer in the same item) which gets recorded for the next round.

When the batch fails or times out, or after ``max_rounds``, the remaining calls
fall back to ordinary synchronous ``messages.create``.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Optional

from loguru import logger

from talk_show_analyzer.config import settings

# USD per million tokens (input, output). Batch = 50% of these.
PRICES = {"haiku": (1.0, 5.0), "sonnet": (3.0, 15.0), "opus": (15.0, 75.0)}
BATCH_DISCOUNT = 0.5

# Optional callback(model, usage, batched: bool) for external cost accounting.
USAGE_HOOK: Optional[Callable[[str, Any, bool], None]] = None


def estimate_cost(model: str, usage: Any, batched: bool) -> float:
    p_in, p_out = next((v for k, v in PRICES.items() if k in model), PRICES["sonnet"])
    cache_w = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_r = getattr(usage, "cache_read_input_tokens", 0) or 0
    usd = (
        usage.input_tokens * p_in
        + cache_w * p_in * 1.25
        + cache_r * p_in * 0.1
        + usage.output_tokens * p_out
    ) / 1e6
    return usd * (BATCH_DISCOUNT if batched else 1.0)


class _Deferred(BaseException):
    """Raised inside an item to stop it at a not-yet-answered LLM call."""


def _key(params: dict) -> str:
    return json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)


def _submit_batch(client, params_list: list[dict]) -> dict[int, Any]:
    """Submit one batch, poll until it ends, return {index: Message} for successes."""
    poll = settings.llm_batch_poll_seconds
    timeout = settings.llm_batch_timeout_seconds
    batch = client.messages.batches.create(
        requests=[{"custom_id": f"r{i}", "params": p} for i, p in enumerate(params_list)]
    )
    logger.info(f"LLM batch {batch.id}: submitted {len(params_list)} request(s)")
    t0 = time.time()
    while batch.processing_status != "ended":
        if time.time() - t0 > timeout:
            try:
                client.messages.batches.cancel(batch.id)
            except Exception:  # noqa: BLE001
                pass
            raise TimeoutError(f"batch {batch.id} not done after {timeout}s")
        time.sleep(poll)
        batch = client.messages.batches.retrieve(batch.id)
    out: dict[int, Any] = {}
    in_tok = out_tok = 0
    usd = 0.0
    for entry in client.messages.batches.results(batch.id):
        if entry.result.type == "succeeded":
            msg = entry.result.message
            out[int(entry.custom_id[1:])] = msg
            in_tok += msg.usage.input_tokens
            out_tok += msg.usage.output_tokens
            usd += estimate_cost(msg.model, msg.usage, batched=True)
            if USAGE_HOOK is not None:
                USAGE_HOOK(msg.model, msg.usage, True)
        else:
            logger.warning(f"LLM batch {batch.id}: {entry.custom_id} -> {entry.result.type}")
    logger.info(
        f"LLM batch {batch.id}: {len(out)}/{len(params_list)} ok in {time.time() - t0:.0f}s, "
        f"{in_tok} in / {out_tok} out tokens, ~${usd:.4f} (batch price)"
    )
    return out


def run_batched(
    analyzers: Any | Iterable[Any],
    fn: Callable[[Any], Any],
    items: list[Any],
    label: str = "",
    max_rounds: int = 3,
) -> list[Any]:
    """Return [fn(item) for item in items], with the LLM calls batched.

    ``analyzers``: object(s) whose ``.client`` attribute ``fn`` uses for
    ``client.messages.create``. All must share one API key.
    """
    objs = list(analyzers) if isinstance(analyzers, (list, tuple)) else [analyzers]
    if not items:
        return []
    real_clients = [o.client for o in objs]
    real = real_clients[0]
    answers: dict[str, Any] = {}
    state = {"mode": "record", "pending": {}}

    def create(**params):
        k = _key(params)
        if k in answers:
            return answers[k]
        if state["mode"] == "record":
            state["pending"].setdefault(k, params)
            raise _Deferred()
        return real.messages.create(**params)  # sync fallback

    proxy = SimpleNamespace(messages=SimpleNamespace(create=create))
    for o in objs:
        o.client = proxy
    try:
        for rnd in range(1, max_rounds + 1):
            state["pending"] = {}
            results: list[Any] = []
            unfinished = 0
            for it in items:
                try:
                    results.append(fn(it))
                except _Deferred:
                    results.append(None)
                    unfinished += 1
            if not state["pending"]:
                return results
            keys = list(state["pending"])
            logger.info(
                f"run_batched[{label}] round {rnd}: {unfinished}/{len(items)} item(s) "
                f"waiting on {len(keys)} request(s)"
            )
            try:
                got = _submit_batch(real, [state["pending"][k] for k in keys])
            except Exception as e:  # noqa: BLE001
                logger.warning(f"run_batched[{label}]: batch failed ({e}); falling back to sync")
                break
            for i, msg in got.items():
                answers[keys[i]] = msg
            if not got:
                break
        # Final pass: answered calls are replayed, anything else runs synchronously.
        state["mode"] = "sync"
        return [fn(it) for it in items]
    finally:
        for o, c in zip(objs, real_clients):
            o.client = c
