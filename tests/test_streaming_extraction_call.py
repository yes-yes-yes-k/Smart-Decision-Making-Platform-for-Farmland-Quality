"""Time budgets of the streaming extraction call."""
import unittest
from types import SimpleNamespace
from unittest import mock

from framework.knowledge_graph.streaming_extraction_call import stream_completion


class Delta(SimpleNamespace):
    pass


def chunk(text=None, reasoning=None, finish=None, usage=None, extra=None):
    delta = SimpleNamespace(content=text, reasoning_content=reasoning)
    if extra is not None:
        delta = SimpleNamespace(content=text, reasoning_content=None)
        delta.model_extra = {"reasoning_content": extra}
    choices = [SimpleNamespace(delta=delta, finish_reason=finish)] if (text or reasoning or finish or extra) else []
    return SimpleNamespace(choices=choices, usage=usage)


class FakeStream:
    def __init__(self, chunks):
        self.chunks, self.closed, self.consumed = chunks, False, 0

    def __iter__(self):
        for item in self.chunks:
            self.consumed += 1
            yield item

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, stream):
        self.stream, self.requests = stream, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.stream


class StreamingCallTests(unittest.TestCase):
    def run_with(self, stream, **overrides):
        arguments = dict(ttft_limit=300, gap_limit=120, total_limit=900, reasoning_token_cap=0)
        arguments.update(overrides)
        return stream_completion(FakeClient(stream), {"model": "m", "messages": []}, **arguments)

    def test_collects_content_usage_and_first_token(self):
        usage = SimpleNamespace(total_tokens=1234)
        stream = FakeStream([chunk("ab", reasoning="想"), chunk("cd"), chunk("ef", finish="stop", usage=usage)])
        result = self.run_with(stream)
        self.assertEqual(result["content"], "abcdef")
        self.assertIs(result["usage"], usage)
        self.assertEqual(result["finish_reason"], "stop")
        self.assertIsNone(result["aborted"])
        self.assertEqual(result["chunks"], 3)
        self.assertIsNotNone(result["ttft_seconds"])
        self.assertTrue(stream.closed)

    def test_requests_streaming_with_usage(self):
        client = FakeClient(FakeStream([chunk("x", finish="stop")]))
        stream_completion(client, {"model": "m"}, ttft_limit=300, gap_limit=120, total_limit=900)
        sent = client.requests[0]
        self.assertTrue(sent["stream"])
        self.assertEqual(sent["stream_options"], {"include_usage": True})

    def test_reasoning_cap_aborts_early_and_closes(self):
        stream = FakeStream([chunk(reasoning="想" * 500) for _ in range(50)])
        result = self.run_with(stream, reasoning_token_cap=100)
        self.assertEqual(result["aborted"], "reasoning_cap_exceeded")
        self.assertLess(result["chunks"], 50)
        self.assertTrue(stream.closed)
        self.assertGreater(result["reasoning_characters"], 0)

    def test_reasoning_cap_off_lets_the_stream_finish(self):
        stream = FakeStream([chunk(reasoning="想" * 500) for _ in range(5)] + [chunk("x", finish="stop")])
        result = self.run_with(stream, reasoning_token_cap=0)
        self.assertIsNone(result["aborted"])

    def test_gap_between_deltas_is_reported_as_a_stall(self):
        clock = iter([0.0, 1.0, 200.0, 200.0, 200.0])
        stream = FakeStream([chunk("a"), chunk("b"), chunk("c", finish="stop")])
        with mock.patch("framework.knowledge_graph.streaming_extraction_call.time.monotonic",
                        side_effect=lambda: next(clock, 200.0)):
            result = self.run_with(stream, gap_limit=120)
        self.assertEqual(result["aborted"], "stream_gap_exceeded")
        self.assertEqual(result["content"], "a")

    def test_slow_first_token_is_reported_as_queueing(self):
        clock = iter([0.0, 500.0, 500.0])
        stream = FakeStream([chunk("a", finish="stop")])
        with mock.patch("framework.knowledge_graph.streaming_extraction_call.time.monotonic",
                        side_effect=lambda: next(clock, 500.0)):
            result = self.run_with(stream, ttft_limit=300)
        self.assertEqual(result["aborted"], "ttft_limit_exceeded")
        self.assertIsNone(result["ttft_seconds"])

    def test_total_limit_stops_a_healthy_but_endless_stream(self):
        clock = iter([0.0, 10.0, 20.0, 30.0, 40.0, 40.0])
        stream = FakeStream([chunk("a"), chunk("b"), chunk("c"), chunk("d")])
        with mock.patch("framework.knowledge_graph.streaming_extraction_call.time.monotonic",
                        side_effect=lambda: next(clock, 40.0)):
            result = self.run_with(stream, total_limit=35)
        self.assertEqual(result["aborted"], "total_time_limit_exceeded")

    def test_stream_without_finish_reason_is_flagged(self):
        result = self.run_with(FakeStream([chunk("a")]))
        self.assertEqual(result["aborted"], "stream_truncated")

    def test_reasoning_in_model_extra_is_counted(self):
        result = self.run_with(FakeStream([chunk(extra="想" * 100), chunk("x", finish="stop")]))
        self.assertGreater(result["reasoning_characters"], 0)

    def test_partial_content_survives_an_abort(self):
        stream = FakeStream([chunk("partial"), chunk(reasoning="想" * 900)])
        result = self.run_with(stream, reasoning_token_cap=100)
        self.assertEqual(result["aborted"], "reasoning_cap_exceeded")
        self.assertEqual(result["content"], "partial")


if __name__ == "__main__":
    unittest.main()
