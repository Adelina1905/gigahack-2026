import json
import unittest
import urllib.error
from unittest.mock import patch

from municipal_rag.api import (
    ManagedApiUnavailable,
    begin_interactive_request,
    chat_json,
    end_interactive_request,
    request_json,
)
from municipal_rag.verification import verify_claims


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class InteractiveResilienceTests(unittest.TestCase):
    def test_interactive_request_does_not_retry_a_timed_out_provider(self) -> None:
        tokens = begin_interactive_request(55, 25, [])
        try:
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")) as call:
                with self.assertRaises(ManagedApiUnavailable):
                    request_json("chat/completions", {"model": "primary"}, "key")
            self.assertEqual(call.call_count, 1)
        finally:
            end_interactive_request(tokens)

    def test_chat_request_contains_model_fallback_and_latency_routing(self) -> None:
        tokens = begin_interactive_request(55, 25, ["fallback/model"])
        response = {"choices": [{"message": {"content": '{"ok":true}'}}], "model": "primary"}
        try:
            with patch("urllib.request.urlopen", return_value=FakeResponse(response)) as call:
                result = chat_json("primary/model", "Return ok", "question", "key")
            payload = json.loads(call.call_args.args[0].data.decode("utf-8"))
            self.assertEqual(payload["models"], ["primary/model", "fallback/model"])
            self.assertEqual(payload["provider"]["sort"], "latency")
            self.assertTrue(result["ok"])
        finally:
            end_interactive_request(tokens)

    def test_claims_are_verified_in_one_managed_call(self) -> None:
        evidence = [
            {"id": "S1", "documentId": "d1", "evidenceKind": "body",
             "title": "Botanica", "exactQuote": "În Botanica lucrările au început."},
            {"id": "S2", "documentId": "d2", "evidenceKind": "body",
             "title": "Ciocana", "exactQuote": "În Ciocana licitația este în evaluare."},
        ]
        claims = [
            {"text": "În Botanica lucrările au început.", "evidenceIds": ["S1"]},
            {"text": "În Ciocana licitația este în evaluare.", "evidenceIds": ["S2"]},
        ]
        managed = {"verdicts": [
            {"index": 0, "supported": True, "reason": "exact"},
            {"index": 1, "supported": True, "reason": "exact"},
        ]}
        with patch("municipal_rag.verification.chat_json", return_value=managed) as call:
            retained, decisions = verify_claims(claims, evidence, "model", "key")
        self.assertEqual(call.call_count, 1)
        self.assertEqual(len(retained), 2)
        self.assertEqual(len(decisions), 2)


if __name__ == "__main__":
    unittest.main()
