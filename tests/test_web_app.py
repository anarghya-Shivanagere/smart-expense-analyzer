from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


class TestWebApp(unittest.TestCase):
    def test_bootstrap_and_analyze_sample_dataset(self) -> None:
        root = Path("runs") / f"test_web_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        previous_db = os.environ.get("APP_DB_URL")
        os.environ["APP_DB_URL"] = str(root / "web.db")
        try:
            from src.web_app import app

            client = TestClient(app)
            bootstrap = client.get("/api/bootstrap")
            self.assertEqual(bootstrap.status_code, 200)
            bootstrap_payload = bootstrap.json()
            self.assertIn("sample", bootstrap_payload["datasets"])

            analyze = client.post("/api/analyze", json={"dataset": "sample", "month": "All", "seed": 42})
            self.assertEqual(analyze.status_code, 200)
            payload = analyze.json()
            self.assertEqual(payload["state"], "REPORTED")
            self.assertIn("categorized_transactions", payload)
            self.assertIn("category_options", payload)
            self.assertIn("anomaly_review_candidates", payload)
        finally:
            if previous_db is None:
                os.environ.pop("APP_DB_URL", None)
            else:
                os.environ["APP_DB_URL"] = previous_db
            shutil.rmtree(root, ignore_errors=True)

    def test_category_corrections_endpoint_updates_transactions(self) -> None:
        root = Path("runs") / f"test_web_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        previous_db = os.environ.get("APP_DB_URL")
        os.environ["APP_DB_URL"] = str(root / "web.db")
        try:
            from src.web_app import app

            client = TestClient(app)
            client.get("/api/bootstrap")
            correction_payload = {
                "dataset": "sample",
                "corrections": [
                    {
                        "date": "2026-02-02",
                        "description": "House rent transfer",
                        "amount": -18000.0,
                        "category": "Transport",
                    }
                ],
            }
            response = client.post("/api/corrections", json=correction_payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["applied"], 1)

            analyze = client.post("/api/analyze", json={"dataset": "sample", "month": "All", "seed": 42})
            categorized = analyze.json()["categorized_transactions"]
            updated_row = next(row for row in categorized if row["description"] == "House rent transfer")
            self.assertEqual(updated_row["category"], "Transport")
        finally:
            if previous_db is None:
                os.environ.pop("APP_DB_URL", None)
            else:
                os.environ["APP_DB_URL"] = previous_db
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
