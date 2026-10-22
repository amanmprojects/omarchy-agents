#!/usr/bin/python3 -I
"""Tests for the OpenCode collector. Run: python3 -I tests/test_opencode_collector.py"""

from __future__ import annotations

import datetime as dt
import importlib.machinery
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COLLECTOR = ROOT / "bin" / "omarchy-agent-usage-opencode"


def load_collector():
  loader = importlib.machinery.SourceFileLoader("omarchy_opencode_collector", str(COLLECTOR))
  spec = importlib.util.spec_from_loader(loader.name, loader)
  if spec is None:
    raise RuntimeError("cannot load collector")
  module = importlib.util.module_from_spec(spec)
  loader.exec_module(module)
  return module


def timestamp(year: int, month: int, day: int, hour: int = 12) -> int:
  return int(dt.datetime(year, month, day, hour).timestamp() * 1000)


def message(role: str, tokens=None, model_id="", provider="", cost=0.0) -> str:
  payload = {"role": role, "modelID": model_id, "providerID": provider, "cost": cost}
  if tokens is not None:
    payload["tokens"] = tokens
  return json.dumps(payload)


def session_message(role: str, tokens=None, model_id="", provider="", cost=0.0) -> str:
  payload = {"role": role, "cost": cost}
  if tokens is not None:
    payload["tokens"] = tokens
  if model_id:
    payload["model"] = {"id": model_id, "providerID": provider}
  return json.dumps(payload)


class Database:
  def __init__(self):
    self.temp = tempfile.TemporaryDirectory()
    self.path = Path(self.temp.name) / "opencode.db"
    self.connection = sqlite3.connect(self.path)
    self.connection.executescript(
      """
      CREATE TABLE message (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        time_created INTEGER NOT NULL,
        time_updated INTEGER NOT NULL,
        data TEXT NOT NULL
      );
      CREATE TABLE session_message (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        type TEXT NOT NULL,
        seq INTEGER NOT NULL,
        time_created INTEGER NOT NULL,
        time_updated INTEGER NOT NULL,
        data TEXT NOT NULL
      );
      """
    )

  def old(self, message_id: str, session: str, created: int, data: str) -> None:
    self.connection.execute(
      "INSERT INTO message VALUES (?, ?, ?, ?, ?)",
      (message_id, session, created, created, data),
    )

  def new(self, message_id: str, session: str, kind: str, created: int, data: str) -> None:
    self.connection.execute(
      "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?, ?)",
      (message_id, session, kind, 0, created, created, data),
    )

  def close(self):
    self.connection.commit()
    self.connection.close()

  def cleanup(self):
    self.temp.cleanup()


class CollectorTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.collector = load_collector()

  def build_database(self) -> Database:
    db = Database()
    db.old("m1", "s1", timestamp(2026, 10, 20), message("user"))
    db.old(
      "m2",
      "s1",
      timestamp(2026, 10, 20),
      message("assistant", {"input": 100, "output": 10, "reasoning": 5, "cache": {"read": 50, "write": 2}}, "model-a", "opencode", 0.01),
    )
    # A migrated message appears in both stores; the live copy has the usage.
    db.old(
      "m3",
      "s3",
      timestamp(2026, 10, 21),
      message("assistant", {"input": 10, "output": 1, "cache": {"read": 0, "write": 0}}, "model-a", "opencode", 0.001),
    )
    db.new(
      "m3",
      "s3",
      "assistant",
      timestamp(2026, 10, 21),
      session_message("assistant", {"input": 30, "output": 3, "cache": {"read": 0, "write": 0}}, "model-a", "opencode", 0.005),
    )
    db.new("m4", "s2", "user", timestamp(2026, 10, 22), session_message("user"))
    db.new(
      "m5",
      "s2",
      "assistant",
      timestamp(2026, 10, 22),
      session_message("assistant", {"input": 200, "output": 20, "cache": {"read": 100, "write": 0}}, "model-b", "openrouter", 0.02),
    )
    # Neither synthetic nor system rows are prompts or usage.
    db.new("m6", "s2", "synthetic", timestamp(2026, 10, 22), session_message("synthetic"))
    db.new("m7", "s2", "system", timestamp(2026, 10, 22), session_message("system"))
    # Malformed JSON is skipped rather than failing the whole scan.
    db.old("m8", "s1", timestamp(2026, 10, 20), "{not json")
    db.close()
    return db

  def test_collects_both_stores_with_deduplication(self):
    db = self.build_database()
    try:
      record = self.collector.collect(db.path, today=dt.date(2026, 10, 22))
    finally:
      db.temp.cleanup()

    self.assertEqual(record["id"], "opencode")
    self.assertTrue(record["ready"])
    self.assertEqual(record["totalPrompts"], 2)
    self.assertEqual(record["totalSessions"], 3)
    self.assertEqual(record["todayPrompts"], 1)
    self.assertEqual(record["todaySessions"], 1)
    self.assertEqual(record["activeDays"], 3)
    self.assertEqual(record["todayTotalTokens"], 320)
    self.assertEqual(record["totalTokens"], 520)
    self.assertEqual(record["modelUsage"]["model-a"]["inputTokens"], 130)
    self.assertEqual(record["modelUsage"]["model-a"]["outputTokens"], 18)
    self.assertEqual(record["modelUsage"]["model-b"]["cacheReadInputTokens"], 100)
    self.assertEqual(record["providerUsage"]["opencode"]["messages"], 2)
    self.assertAlmostEqual(record["costUsd"], 0.035)
    self.assertEqual([day["date"] for day in record["recentDays"]], [
      "2026-10-16", "2026-10-17", "2026-10-18", "2026-10-19",
      "2026-10-20", "2026-10-21", "2026-10-22",
    ])
    by_date = {day["date"]: day["messageCount"] for day in record["recentDays"]}
    self.assertEqual(by_date["2026-10-20"], 167)
    self.assertEqual(by_date["2026-10-21"], 33)
    self.assertEqual(by_date["2026-10-22"], 320)

  def test_missing_database_is_a_quiet_empty_record(self):
    with tempfile.TemporaryDirectory() as temp:
      record = self.collector.collect(Path(temp) / "missing.db", today=dt.date(2026, 10, 22))
    self.assertFalse(record["ready"])
    self.assertEqual(record["totalSessions"], 0)
    self.assertEqual(len(record["recentDays"]), 7)

  def test_empty_database_is_valid(self):
    with tempfile.TemporaryDirectory() as temp:
      path = Path(temp) / "opencode.db"
      connection = sqlite3.connect(path)
      connection.executescript(
        "CREATE TABLE message (id TEXT, session_id TEXT, time_created INTEGER, data TEXT);"
        "CREATE TABLE session_message (id TEXT, session_id TEXT, type TEXT, time_created INTEGER, data TEXT);"
      )
      connection.close()
      record = self.collector.collect(path, today=dt.date(2026, 10, 22))
    self.assertFalse(record["ready"])
    self.assertEqual(record["totalTokens"], 0)


if __name__ == "__main__":
  unittest.main()
