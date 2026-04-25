from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from agent import sms_sender


class SmsWarmLeadGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parent / "_tmp_sms_gate"
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.phone_map_path = self.root / "contact_phone_map.json"
        self.phone_map_path.write_text(
            json.dumps({"+251711704273": "prospect@example.com"}),
            encoding="utf-8",
        )
        self.sms_log_path = self.root / "sms_log.jsonl"

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_sms_refused_without_qualified_email_reply(self) -> None:
        with patch.object(sms_sender, "PHONE_MAP_PATH", self.phone_map_path):
            with patch.object(sms_sender, "SMS_LOG_PATH", self.sms_log_path):
                with patch.object(sms_sender, "is_opted_out", return_value=False):
                    with patch.object(sms_sender, "has_recent_event_for_email", return_value=False):
                        with patch.object(sms_sender, "record_contact_event", return_value={"mode": "simulated"}):
                            result = sms_sender.send_sms("+251711704273", "Warm lead SMS test")

        self.assertEqual(result["sent_or_simulated"], "refused")
        self.assertEqual(result["refused"], "cold contact")

    def test_sms_allowed_after_qualified_email_reply(self) -> None:
        with patch.object(sms_sender, "PHONE_MAP_PATH", self.phone_map_path):
            with patch.object(sms_sender, "SMS_LOG_PATH", self.sms_log_path):
                with patch.object(sms_sender, "is_opted_out", return_value=False):
                    with patch.object(sms_sender, "has_recent_event_for_email", return_value=True):
                        with patch.object(sms_sender, "record_contact_event", return_value={"mode": "simulated"}):
                            result = sms_sender.send_sms("+251711704273", "Warm lead SMS test")

        self.assertEqual(result["sent_or_simulated"], "simulated")
        self.assertEqual(result["delivery_status"], "simulated")


if __name__ == "__main__":
    unittest.main()
