"""Streaming extraction call with observable time budgets.

A non-streaming request exposes exactly one number: how long until the whole
body arrives. Queueing, prefill and reasoning all collapse into that number,
so a deadline can only ever say "too slow" — never why. Streaming splits the
same request into measurable phases and lets each one be bounded separately:

* ``ttft_seconds`` — request accepted to first delta (queue + prefill + the
  first reasoning token). Large value means the provider held the request.
* inter-chunk gap — a stall mid-generation rather than a slow start.
* total wall clock — the only bound a non-streaming call ever had.
* live reasoning estimate — aborts a runaway chain of thought while it is
  still cheap, instead of discovering it after the fact.

Aborting never raises away the partial content: the caller keeps whatever
arrived, marked with a stable reason code, so a truncated record is auditable
rather than lost.
"""
from __future__ import annotations

import time

REASONS = {
    "ttft_limit_exceeded": "no first delta inside the first-token budget",
    "stream_gap_exceeded": "the stream stalled between deltas",
    "total_time_limit_exceeded": "wall clock budget exhausted while streaming",
    "reasoning_cap_exceeded": "reasoning estimate passed the configured ceiling",
    "stream_truncated": "the stream ended before a finish reason was reported",
}

# Reasoning text is denser than prose: the probe on 1149 measured 4,719
# characters for 1,025 reasoning tokens (4.6). 4.0 keeps the live estimate
# about 15% above the real count, so a cap fires slightly early, never late.
CHARS_PER_TOKEN = 4.0


def reasoning_delta(delta) -> str:
    """Reasoning text from a delta, tolerating SDK field placement."""
    value = getattr(delta, "reasoning_content", None)
    if not value:
        extra = getattr(delta, "model_extra", None) or {}
        value = extra.get("reasoning_content") or extra.get("reasoning")
    return value or ""


def estimate_tokens(characters: int, chars_per_token: float = CHARS_PER_TOKEN) -> int:
    return int(characters / chars_per_token) if characters else 0


def stream_completion(client, request: dict, *, ttft_limit: float, gap_limit: float,
                      total_limit: float, reasoning_token_cap: int = 0,
                      chars_per_token: float = CHARS_PER_TOKEN) -> dict:
    """Run one streaming completion and report where the time went.

    The transport timeout must be at least ``gap_limit`` so the gap check owns
    the decision; a shorter transport timeout would raise before the counters
    could explain why.
    """
    started = time.monotonic()
    payload = dict(request, stream=True, stream_options={"include_usage": True})
    stream = client.chat.completions.create(**payload)
    content, usage, finish_reason = [], None, None
    first_at, last_at, chunks = None, started, 0
    reasoning_characters = 0
    aborted = None
    try:
        for chunk in stream:
            now = time.monotonic()
            if first_at is None:
                if now - started > ttft_limit:
                    aborted = "ttft_limit_exceeded"
                    break
                first_at = now
            elif now - last_at > gap_limit:
                aborted = "stream_gap_exceeded"
                break
            if now - started > total_limit:
                aborted = "total_time_limit_exceeded"
                break
            last_at = now
            chunks += 1
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage
            for choice in (getattr(chunk, "choices", None) or []):
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    reasoning = reasoning_delta(delta)
                    if reasoning:
                        reasoning_characters += len(reasoning)
                        if reasoning_token_cap and estimate_tokens(
                                reasoning_characters, chars_per_token) > reasoning_token_cap:
                            aborted = "reasoning_cap_exceeded"
                    text = getattr(delta, "content", None)
                    if text:
                        content.append(text)
                if getattr(choice, "finish_reason", None):
                    finish_reason = choice.finish_reason
            if aborted:
                break
    finally:
        closer = getattr(stream, "close", None)
        if callable(closer):
            try:
                closer()
            except Exception:
                pass

    if aborted is None and finish_reason is None:
        aborted = "stream_truncated"
    elapsed = round(time.monotonic() - started, 2)
    return {"content": "".join(content), "usage": usage,
            "ttft_seconds": None if first_at is None else round(first_at - started, 2),
            "gap_seconds": round(last_at - started, 2) if chunks else None,
            "seconds": elapsed, "chunks": chunks, "finish_reason": finish_reason,
            "reasoning_characters": reasoning_characters,
            "reasoning_tokens_estimated": estimate_tokens(reasoning_characters, chars_per_token),
            "aborted": aborted, "reason": REASONS.get(aborted or "", None)}
