"""
constants.py
============
Controlled vocabulary enums for the feedback analyzer.
All modules that need Category, Priority, Sentiment, or ProcessingStatus
import from here — never use raw strings for these values.
"""

from enum import Enum


class Category(str, Enum):
    """Customer intent categories assigned by the LLM."""

    BUG_REPORT = "Bug Report"
    FEATURE_REQUEST = "Feature Request"
    BILLING_ISSUE = "Billing Issue"
    GENERAL_INQUIRY = "General Inquiry"


class Priority(str, Enum):
    """Business priority assigned by the LLM based on urgency and impact."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"


class Sentiment(str, Enum):
    """Customer sentiment detected by the LLM from the message tone."""

    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    NEGATIVE = "Negative"


class ProcessingStatus(str, Enum):
    """Final outcome recorded in the database for every input record."""

    PROCESSED = "PROCESSED"  # LLM analysis succeeded; analysis_results row exists
    IGNORED = "IGNORED"      # Filtered out (greeting / spam / promotional)
    INVALID = "INVALID"      # Failed input validation (missing fields, bad types)
    FAILED = "FAILED"        # Passed validation + filter but LLM or DB step errored
