"""
Vision module — Phase 7 image classification and parsing.

Provides three public entry points called from the ingestor and backfill script:
  classify_image()      → "chart_zone" | "mt5_screenshot" | "other"
  parse_chart_zone()    → ParsedSignal (zone_estimated) or None
  parse_mt5_screenshot() → ScreenshotData or None

Cross-checking a screenshot claim against MT5 price data is handled by
screenshot_checker.cross_check_screenshot().
"""

from backend.vision.classifier import classify_image
from backend.vision.chart_parser import parse_chart_zone
from backend.vision.screenshot_parser import parse_mt5_screenshot, ScreenshotData

__all__ = [
    "classify_image",
    "parse_chart_zone",
    "parse_mt5_screenshot",
    "ScreenshotData",
]
