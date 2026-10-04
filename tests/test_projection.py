import unittest

from axiom_ui import ProjectionError, chart_context, project_data_layer, unavailable_layer


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.query = {"fields": ["close"], "symbols": ["A"],
                      "sessions": ["2025-01-02"], "purpose": "decision_facts",
                      "price_basis": "unadjusted", "adjustment_anchor": None}
        self.batch = {"records": [{"security_id": "A", "session": "2025-01-02", "close": 10}],
                      "field_meta": {"close": {"dtype": "float64", "unit": "CNY/share",
                                               "by_key": [{"security_id": "A", "session": "2025-01-02",
                                                           "usable_from": "2025-01-02T10:00:00Z",
                                                           "first_observed_at": "2025-01-02T11:00:00Z",
                                                           "missing_reason": None}]}},
                      "context": {"contract_version": "data_batch_v1", "snapshot_id": "s1",
                                  "domain": "daily_bars", "reader_version": "local_reader_v1",
                                  "query": self.query, "limitations": []}}

    def test_data_layer_and_unavailable_feature(self):
        chart = chart_context(mode="run_replay", security_id="A",
            session_refs={"2025-01-02": {"snapshot_id": "s1", "query": self.query,
                                         "reader_version": "local_reader_v1"}},
            price_basis="unadjusted", adjustment_anchor=None,
            time_axis="decision_available", generated_at="2026-01-01T00:00:00Z")
        layer = project_data_layer(self.batch, field="close", security_id="A",
                                   role="candles", chart=chart,
                                   generated_at="2026-01-01T00:00:00Z")
        self.assertEqual(layer["points"][0]["source_available_time"],
                         "2025-01-02T10:00:00Z")
        self.assertEqual(layer["generated_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(layer["stage"], "canonical")
        self.assertEqual(unavailable_layer(role="feature", requested_ref="fb1",
                                           requested_stage="base", unit="ratio")["status"],
                         "LAYER_UNAVAILABLE")
        self.assertEqual(layer["freshness"]["last_observed_time"], "2025-01-02T11:00:00Z")

    def test_rejects_unknown_data_contract(self):
        self.batch["context"]["contract_version"] = "future"
        with self.assertRaisesRegex(ProjectionError, "incompatible"):
            project_data_layer(self.batch, field="close", security_id="A", role="candles")


if __name__ == "__main__":
    unittest.main()
