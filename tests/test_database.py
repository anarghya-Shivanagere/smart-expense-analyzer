from __future__ import annotations

import unittest
import uuid
import shutil
from pathlib import Path

from src.database import (
    add_categories,
    apply_category_corrections,
    import_csv_to_dataset,
    init_db,
    load_anomaly_feedback,
    list_datasets,
    list_custom_categories,
    list_months,
    load_merchant_rules,
    load_transactions,
    save_anomaly_feedback,
)


class TestDatabase(unittest.TestCase):
    def test_import_and_filter_by_month(self) -> None:
        root = Path("runs") / f"test_db_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        try:
            db = root / "test.db"
            csv_path = root / "input.csv"
            csv_path.write_text(
                "date,description,amount,category\n"
                "2026-01-01,grocery,-100,Food\n"
                "2026-01-15,uber,-200,Uncategorized\n"
                "2026-02-01,rent,-1000,Rent\n",
                encoding="utf-8",
            )

            init_db(db)
            count = import_csv_to_dataset(db, csv_path, "demo")
            self.assertEqual(count, 3)
            self.assertIn("demo", list_datasets(db))
            self.assertEqual(list_months(db, "demo"), ["2026-01", "2026-02"])

            jan = load_transactions(db, "demo", "2026-01")
            feb = load_transactions(db, "demo", "2026-02")
            self.assertEqual(len(jan), 2)
            self.assertEqual(len(feb), 1)
            self.assertEqual(jan[0].category, "Food")
            self.assertEqual(jan[1].category, "Uncategorized")
            memory = load_merchant_rules(db)
            self.assertIn("grocery", memory)

            applied = apply_category_corrections(
                db,
                "demo",
                [
                    {
                        "date": "2026-01-15",
                        "description": "uber",
                        "amount": -200.0,
                        "category": "Transport",
                    }
                ],
            )
            self.assertEqual(applied, 1)
            updated = load_transactions(db, "demo", "2026-01")
            self.assertEqual(updated[1].category, "Transport")
            add_categories(db, [("Pets", "2026-01-01T00:00:00+00:00", "manual")])
            self.assertIn("Pets", list_custom_categories(db))
            saved = save_anomaly_feedback(
                db,
                "demo",
                "run-1",
                [
                    {
                        "date": "2026-01-15",
                        "description": "uber",
                        "amount": 200.0,
                        "feedback": "Normal",
                    }
                ],
            )
            self.assertEqual(saved, 1)
            feedback = load_anomaly_feedback(db, "demo")
            self.assertEqual(feedback[("2026-01-15", "uber", 200.0)], "Normal")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
