"""Shared category definitions for categorization components."""

from __future__ import annotations

from typing import Dict, Iterable


CATEGORY_KEYWORDS: Dict[str, Iterable[str]] = {
    "Food": (
        "restaurant", "cafe", "grocery", "groceries", "food", "swiggy", "zomato", "uber eats",
        "starbucks", "mcdonalds", "bakery", "whole foods", "walmart groceries", "costco bulk groceries",
        "doordash", "pizza", "subway", "kfc", "coffee", "lunch", "dinner", "snacks",
    ),
    "Transport": (
        "uber", "ola", "lyft", "fuel", "petrol", "diesel", "metro", "bus", "train", "parking",
        "gas station", "shell", "ticket fine",
    ),
    "Utilities": ("electricity", "water", "internet", "wifi", "mobile", "bill"),
    "Shopping": (
        "amazon", "flipkart", "mall", "store", "clothing", "electronics", "target", "ikea", "best buy",
        "furniture", "laptop", "shopping", "duty free", "household",
    ),
    "Entertainment": (
        "movie", "netflix", "spotify", "prime", "hotstar", "game", "youtube premium", "disney+",
        "cinema", "concert", "ticket",
    ),
    "Healthcare": ("pharmacy", "hospital", "clinic", "medical", "doctor", "dentist", "prescription"),
    "Rent": ("rent", "landlord", "lease"),
    "Salary": ("salary", "payroll", "income", "credit from employer"),
    "Travel": ("flight", "airlines", "airline", "hotel", "marriott", "hilton", "airbnb", "airport", "lufthansa", "delta"),
    "Education": ("course", "udemy", "coursera", "tuition", "textbook", "textbooks", "school", "bookstore"),
    "Financial": ("interest charge", "service fee", "bank fee", "loan repayment", "atm withdrawal fee", "fee", "insurance premium", "insurance"),
    "Fitness": ("gym", "membership", "workout", "fitness"),
}

AVAILABLE_CATEGORIES: tuple[str, ...] = tuple(CATEGORY_KEYWORDS.keys()) + ("Other",)
