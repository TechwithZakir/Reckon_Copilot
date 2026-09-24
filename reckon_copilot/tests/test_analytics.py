from __future__ import annotations

import unittest

from reckon_copilot.agents.analytics import (
    AnalyticsLimits,
    InMemoryAnalyticsDataSource,
    run_analytics,
)
from reckon_copilot.permissions.boundary import PermissionDenied, StaticPermissionAdapter
from reckon_copilot.providers.usage import InMemoryUsageLogger


class AnalyticsAgentTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"name": "SO-1", "customer": "Crystal Traders", "posting_date": "2026-09-01", "grand_total": 100},
            {"name": "SO-2", "customer": "Crystal Traders", "posting_date": "2026-09-02", "grand_total": 150},
            {"name": "SO-3", "customer": "Northwind", "posting_date": "2026-09-02", "grand_total": 80},
        ]
        self.context = {
            "page_type": "List",
            "doctype": "Sales Order",
            "filters": {},
            "fingerprint": "analytics-test",
        }
        self.adapter = StaticPermissionAdapter(
            doctype_permissions={("Sales Order", "read"): True},
        )

    def test_summary_returns_bounded_table_and_narrative(self):
        result = run_analytics(
            "Summarize this list",
            self.context,
            permission_adapter=self.adapter,
            data_source=InMemoryAnalyticsDataSource(self.rows),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["agent"], "analytics")
        self.assertEqual(result["row_count"], 3)
        self.assertIn("permitted records", result["narrative"])
        self.assertLessEqual(len(result["table"]["rows"]), 20)
        self.assertIsNone(result["chart"])

    def test_breakdown_returns_chart_ready_data(self):
        result = run_analytics(
            "Show sales by customer",
            self.context,
            permission_adapter=self.adapter,
            data_source=InMemoryAnalyticsDataSource(self.rows),
        )

        self.assertEqual(result["intent"], "breakdown")
        self.assertEqual(result["chart"]["type"], "bar")
        self.assertEqual(result["chart"]["labels"], ["Crystal Traders", "Northwind"])
        self.assertEqual(result["chart"]["datasets"][0]["data"], [250.0, 80.0])
        self.assertEqual(result["table"]["rows"][0]["group"], "Crystal Traders")

    def test_trend_uses_date_dimension_and_logs_usage(self):
        logger = InMemoryUsageLogger()
        result = run_analytics(
            "Show the trend over time",
            self.context,
            permission_adapter=self.adapter,
            data_source=InMemoryAnalyticsDataSource(self.rows),
            usage_logger=logger,
        )

        self.assertEqual(result["intent"], "trend")
        self.assertEqual(result["chart"]["type"], "line")
        self.assertEqual(result["chart"]["labels"], ["2026-09-01", "2026-09-02"])
        self.assertEqual(len(logger.records), 1)
        self.assertEqual(logger.records[0].capability, "analytics.run")

    def test_permission_boundary_blocks_restricted_data(self):
        with self.assertRaises(PermissionDenied):
            run_analytics(
                "Summarize this list",
                self.context,
                permission_adapter=StaticPermissionAdapter(),
                data_source=InMemoryAnalyticsDataSource(self.rows),
            )

    def test_row_limit_is_enforced_before_analysis(self):
        result = run_analytics(
            "Summarize this list",
            self.context,
            permission_adapter=self.adapter,
            data_source=InMemoryAnalyticsDataSource(self.rows),
            limits=AnalyticsLimits(max_rows=1),
        )

        self.assertEqual(result["row_count"], 1)
        self.assertLessEqual(len(result["table"]["rows"]), 1)

    def test_free_form_sql_request_stays_on_allowlisted_tool(self):
        result = run_analytics(
            "Run SQL against every sales table and summarize it",
            self.context,
            permission_adapter=self.adapter,
            data_source=InMemoryAnalyticsDataSource(self.rows),
        )

        self.assertEqual(result["tool"], "summarize_current_page")
        self.assertNotIn("sql", result["narrative"].lower())

    def test_dashboard_snapshot_produces_compact_table(self):
        result = run_analytics(
            "Explain the dashboard metrics",
            {
                "page_type": "Dashboard",
                "dashboard_name": "Stock",
                "filters": {},
                "dashboard_snapshot": {
                    "title": "Stock",
                    "number_cards": [{"title": "Total Stock Value", "value": 1250}],
                    "charts": [],
                },
            },
            permission_adapter=StaticPermissionAdapter(dashboards={"Stock"}),
            data_source=InMemoryAnalyticsDataSource(),
        )

        self.assertEqual(result["engine"], "dashboard_snapshot")
        self.assertEqual(result["table"]["rows"], [{"metric": "Total Stock Value", "value": 1250}])

    def test_dashboard_chart_is_bounded_and_label_aligned(self):
        result = run_analytics(
            "Show the dashboard trend",
            {
                "page_type": "Dashboard",
                "dashboard_name": "Stock",
                "dashboard_snapshot": {
                    "title": "Stock",
                    "number_cards": [],
                    "charts": [
                        {
                            "title": "Stock trend",
                            "kind": "line",
                            "data": {
                                "labels": ["Jan", "Feb", "Mar"],
                                "series": [
                                    {"name": "Value", "values": [10, 20]},
                                    {"name": "Units", "values": [1, 2, 3]},
                                ],
                            },
                        }
                    ],
                },
            },
            permission_adapter=StaticPermissionAdapter(dashboards={"Stock"}),
            data_source=InMemoryAnalyticsDataSource(),
        )

        self.assertEqual(result["chart"]["type"], "line")
        self.assertEqual(result["chart"]["labels"], ["Jan", "Feb"])
        self.assertEqual([len(item["data"]) for item in result["chart"]["datasets"]], [2, 2])


if __name__ == "__main__":
    unittest.main()
