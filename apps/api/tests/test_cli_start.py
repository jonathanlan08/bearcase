"""`bearcase start` runs migrate, then doctor, then serve, and stops before serving when doctor fails."""

from __future__ import annotations

import argparse

from bearcase import cli


def test_start_serves_when_doctor_passes(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(cli, "cmd_migrate", lambda a: calls.append("migrate") or 0)
    monkeypatch.setattr(cli, "cmd_doctor", lambda a: calls.append("doctor") or 0)
    monkeypatch.setattr(cli, "cmd_serve", lambda a: calls.append("serve") or 0)
    assert cli.cmd_start(argparse.Namespace(host="0.0.0.0", port=8000, reload=False)) == 0
    assert calls == ["migrate", "doctor", "serve"]


def test_start_stops_when_doctor_fails(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(cli, "cmd_migrate", lambda a: calls.append("migrate") or 0)
    monkeypatch.setattr(cli, "cmd_doctor", lambda a: calls.append("doctor") or 1)
    monkeypatch.setattr(cli, "cmd_serve", lambda a: calls.append("serve") or 0)
    assert cli.cmd_start(argparse.Namespace(host="0.0.0.0", port=8000, reload=False)) == 1
    assert calls == ["migrate", "doctor"]


def test_start_is_a_subcommand(monkeypatch):
    monkeypatch.setattr(cli, "cmd_start", lambda a: 0)
    # parser wiring: `start` accepts host and port like `serve`
    parser_ok = cli.main(["start", "--host", "0.0.0.0", "--port", "8000"])
    assert parser_ok == 0
