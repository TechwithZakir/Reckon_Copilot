from __future__ import annotations

import unittest

from reckon_copilot.agents.analytics import InMemoryAnalyticsDataSource
from reckon_copilot.agents.forecasting import ForecastingLimits, run_forecasting
from reckon_copilot.permissions.boundary import PermissionDenied, StaticPermissionAdapter
from reckon_copilot.providers.usage import InMemoryUsageLogger


class ForecastingAgentTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"name": "SO-1", "posting_date": "2026-09-01", "grand_total": 100},
            {"name": "SO-2", "posting_date": "2026-09-02", "grand_total": 150},
            {"name": "SO-3", "posting_date": "2026-09-03", "grand_total": 200},
        ]
        self.context = {
            "page_type": "List",
            "doctype": "Sales Order",
            "filters": {},
            "fingerprint": "forecasting-test",
        }
        self.adapter = StaticPermissionAdapter(
            doctype_permissions={("Sales Order", "read"): True},
        )

    def test_forecast_is_human_readable_and_bounded(self):
        logger = InMemoryUsageLogger()
        source = InMemoryAnalyticsDataSource(self.rows)
        result = run_forecasting(
            "What should sales look like next?",
            self.context,
            permission_adapter=self.adapter,
            data_source=source,
            usage_logger=logger,
            limits=ForecastingLimits(horizon=2),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["agent"], "forecasting")
        self.assertEqual(result["intent"], "forecast")
        self.assertEqual(result["forecast"]["values"], [250.0, 300.0])
        self.assertIn("short-term outlook", result["narrative"])
        self.assertEqual(result["safety"], {
            "read_only": True,
            "writes": False,
            "model_training": False,
            "method": "deterministic bounded calculation",
        })
        self.assertEqual(source.rows, self.rows)
        self.assertEqual(logger.records[0].capability, "forecasting.run")

    def test_anomaly_detection_flags_recent_outlier(self):
        rows = [
            {"posting_date": "2026-09-01", "grand_total": 10},
            {"posting_date": "2026-09-02", "grand_total": 11},
            {"posting_date": "2026-09-03", "grand_total": 50},
        ]
        result = run_forecasting(
            "Find unusual sales values",
            self.context,
            mode="anomalies",
            permission_adapter=self.adapter,
            data_source=InMemoryAnalyticsDataSource(rows),
        )

        self.assertEqual(result["intent"], "anomaly")
        self.assertEqual(result["anomalies"][0]["period"], "2026-09-03")
        self.assertEqual(result["anomalies"][0]["severity"], "high")
        self.assertIn("unusual", result["narrative"])

    def test_dashboard_chart_series_can_be_forecast(self):
        context = {
            "page_type": "Dashboard",
            "dashboard_name": "Sales Dashboard",
            "filters": {},
            "dashboard_snapshot": {
                "title": "Sales Dashboard",
                "charts": [{
                    "title": "Monthly sales",
                    "data": {
                        "labels": ["2026-07-01", "2026-08-01", "2026-09-01"],
                        "series": [{"name": "Sales", "values": [10, 20, 30]}],
                    },
                }],
            },
        }
        adapter = StaticPermissionAdapter(dashboards={"Sales Dashboard"})
        result = run_forecasting(
            "Forecast the dashboard",
            context,
            permission_adapter=adapter,
        )

        self.assertEqual(result["source"], "Current dashboard")
        self.assertEqual(result["forecast"]["values"], [40.0, 50.0, 60.0])
        self.assertEqual(result["chart"]["type"], "line")

    def test_insufficient_history_returns_safe_message(self):
        result = run_forecasting(
            "Forecast this list",
            self.context,
            permission_adapter=self.adapter,
            data_source=InMemoryAnalyticsDataSource(self.rows[:2]),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["forecast"], {})
        self.assertIn("at least 3 are needed", result["narrative"])

    def test_permission_boundary_blocks_restricted_data(self):
        with self.assertRaises(PermissionDenied):
            run_forecasting(
                "Forecast this list",
                self.context,
                permission_adapter=StaticPermissionAdapter(),
                data_source=InMemoryAnalyticsDataSource(self.rows),
            )


if __name__ == "__main__":
    unittest.main()
