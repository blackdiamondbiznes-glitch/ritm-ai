from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import restore_db


def test_restore_requires_explicit_confirmation(tmp_path: Path, monkeypatch, capsys) -> None:
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"dump")
    monkeypatch.setattr(
        restore_db.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("buyruq bajarildi")),
    )

    result = restore_db.restore_dump(
        dump,
        "postgresql://user:secret@db.example/ritm",
        confirm_empty_target=False,
    )

    assert result == 2
    assert "--confirm-empty-target" in capsys.readouterr().err


def test_restore_uses_an_empty_target_and_never_puts_password_in_arguments(
    tmp_path: Path, monkeypatch
) -> None:
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"dump")
    commands: list[tuple[list[str], dict]] = []

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        commands.append((command, kwargs))
        stdout = "0\n" if command[0] == "/tools/psql" else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(restore_db.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(restore_db.subprocess, "run", fake_run)

    result = restore_db.restore_dump(
        dump,
        "postgresql+asyncpg://user:secret@db.example:5432/ritm?ssl=true",
        confirm_empty_target=True,
    )

    assert result == 0
    assert "RESTORE_DATABASE_URL" not in commands[0][1]["env"]
    assert "PGPASSWORD" not in commands[0][1]["env"]
    restore_command, restore_kwargs = commands[-1]
    assert "--single-transaction" in restore_command
    assert "--clean" not in restore_command
    assert "secret" not in " ".join(restore_command)
    assert restore_kwargs["env"]["PGPASSWORD"] == "secret"
    assert restore_kwargs["env"]["PGSSLMODE"] == "require"


def test_restore_refuses_a_nonempty_target(tmp_path: Path, monkeypatch, capsys) -> None:
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"dump")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        stdout = "3\n" if command[0] == "/tools/psql" else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(restore_db.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(restore_db.subprocess, "run", fake_run)

    result = restore_db.restore_dump(
        dump,
        "postgresql://user:secret@db.example/ritm",
        confirm_empty_target=True,
    )

    assert result == 2
    assert not any(
        command[0] == "/tools/pg_restore" and "--single-transaction" in command
        for command in commands
    )
    assert "bo‘sh emas" in capsys.readouterr().err
