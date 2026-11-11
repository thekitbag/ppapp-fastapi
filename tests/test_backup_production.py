"""Exercise backup safety without connecting to production."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.fixture
def backup():
    spec = importlib.util.spec_from_file_location('backup_production', Path(__file__).resolve().parents[1] / 'scripts/backup_production.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preview_never_connects_or_writes(backup, tmp_path, monkeypatch, capsys):
    output = tmp_path / 'new' / 'backup.dump'
    monkeypatch.setattr(sys, 'argv', ['backup', '--output', str(output), '--show-command'])
    def forbidden(*args, **kwargs):
        pytest.fail('Preview must not start child processes')
    monkeypatch.setattr(backup.subprocess, 'run', forbidden)
    assert backup.main() == 0
    assert '--format=custom' in capsys.readouterr().out
    assert not output.parent.exists()


def test_existing_backup_is_never_overwritten(backup, tmp_path, monkeypatch):
    output = tmp_path / 'existing.dump'
    output.write_bytes(b'original archive')
    monkeypatch.setattr(sys, 'argv', ['backup', '--output', str(output)])
    with pytest.raises(RuntimeError, match='already exists'):
        backup.main()
    assert output.read_bytes() == b'original archive'


@pytest.mark.parametrize('dump_status,restore_status', [(1, 0), (0, 1), (0, 0)])
def test_failures_cannot_produce_verified_backup_or_expose_password(
    backup, tmp_path, monkeypatch, capsys, dump_status, restore_status
):
    monkeypatch.setattr(backup, 'ROOT', tmp_path)
    for relative in ['.venv/pg17-client/pg_dump.exe', '.venv/pg17-client/pg_restore.exe', '.venv/flyctl/flyctl.exe']:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    output = tmp_path / 'archives' / 'backup.dump'
    monkeypatch.setattr(sys, 'argv', ['backup', '--output', str(output)])
    monkeypatch.delenv('PGPASSWORD', raising=False)
    secret = 'secret-with-shell-$-and-quotes'
    def run(args, **kwargs):
        assert secret not in str(args)
        if '--version' in args:
            return subprocess.CompletedProcess(args, 0, stdout='pg client (PostgreSQL) 17.11')
        if 'ssh' in args:
            return subprocess.CompletedProcess(args, 0, stdout=backup.json.dumps({'password': secret}))
        if '--list' in args:
            assert 'env' not in kwargs
            return subprocess.CompletedProcess(args, restore_status, stdout=b'; archive listing')
        assert kwargs['env']['PGPASSWORD'] == secret
        assert kwargs['env']['PGSSLMODE'] == 'require'
        assert kwargs['env']['PGCHANNELBINDING'] == 'require'
        kwargs['stdout'].write(b'PGDMP\x00\x80\xffbinary archive')
        return subprocess.CompletedProcess(args, dump_status, stderr=secret.encode())
    monkeypatch.setattr(backup.subprocess, 'run', run)
    if dump_status or restore_status:
        with pytest.raises(RuntimeError):
            backup.main()
        assert not output.with_suffix('.dump.sha256').exists()
    else:
        assert backup.main() == 0
        assert output.with_suffix('.dump.sha256').exists()
        assert output.read_bytes() == b'PGDMP\x00\x80\xffbinary archive'
    assert 'PGPASSWORD' not in backup.os.environ
    assert secret not in capsys.readouterr().out
