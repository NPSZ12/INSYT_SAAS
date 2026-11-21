"""Early-exit guardrails: stop after a decisive signature, never use names."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'backend').is_dir() and (p/'frontend').is_dir())
sys.path.insert(0, str(ROOT/'backend'))
from app.services.structured_intake import json_detector, promotion_profile


class EarlyExitTests(unittest.TestCase):
    def test_decisive_vendor_stops_node_traversal(self):
        def nodes(*args, **kwargs):
            yield {"name":"spaces/s1/messages/m1", "createTime":"now", "sender":{"name":"users/u1"}}
            raise AssertionError("Traversed after definitive Google Chat signal")
        with patch.object(json_detector, "_nodes", nodes):
            self.assertEqual(json_detector.detect_json_profile(source_path=Path('salesforce.json'), payload={}), 'google')

    def test_jsonl_stops_after_definitive_record(self):
        raw=(b'{"type":"message","ts":"1.0","text":"hi","user":"U1"}\n'
             b'BROKEN NOT JSON\n')
        self.assertEqual(promotion_profile.classify_promoted_json(raw,'google_chat.jsonl','.jsonl'),'slack')

    def test_plain_first_does_not_hide_later_vendor(self):
        raw=(b'{"first_name":"One","last_name":"Two"}\n'
             b'{"name":"spaces/a/messages/b","createTime":"now","sender":{"name":"users/u1"}}\n')
        self.assertEqual(promotion_profile.classify_promoted_json(raw,'unknown.ndjson','.ndjson'),'google')

    def test_generic_lookalike_not_vendor(self):
        raw=b'{"messages":[{"text":"hi","sender":"someone"}]}'
        self.assertEqual(promotion_profile.classify_promoted_json(raw,'slack.json','.json'),'custom_api')

    def test_conflict_in_same_node_routes_custom(self):
        raw=(b'{"teamId":"x","channelId":"y","name":"spaces/a/messages/b",'
             b'"createTime":"now","sender":{"name":"users/u"}}')
        self.assertEqual(promotion_profile.classify_promoted_json(raw,'whatever.json','.json'),'custom_api')

if __name__ == '__main__':
    unittest.main()
