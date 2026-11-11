"""Explicitly invoked pre-deploy pg_dump; credentials never enter shell arguments.

Reads DATABASE_URL's password through authenticated Fly SSH into process memory,
uses the independently verified direct Neon endpoint, then checks the archive.
Does not deploy, run migrations, or restore anything.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
POOL = 'ep-wandering-silence-ab67kued-pooler.eu-west-2.aws.neon.tech'
HOST = 'ep-wandering-silence-ab67kued.eu-west-2.aws.neon.tech'
DATABASE = 'neondb'
ROLE = 'neondb_owner'


def command(pg_dump):
    return [str(pg_dump), '--format=custom', '--host='+HOST, '--port=5432',
            '--username='+ROLE, '--dbname='+DATABASE, '--no-password']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--show-command', action='store_true', help='Show the command without connecting or writing files')
    args = parser.parse_args()
    pg_dump = ROOT / '.venv/pg17-client/pg_dump.exe'
    pg_restore = ROOT / '.venv/pg17-client/pg_restore.exe'
    fly = ROOT / '.venv/flyctl/flyctl.exe'
    output = args.output.expanduser().resolve()
    if args.show_command:
        print(subprocess.list2cmdline(command(pg_dump) + ['--file='+str(output)]))
        print('PGSSLMODE=require; PGCHANNELBINDING=require; password supplied only in the child process environment.')
        return 0
    if output.exists():
        raise RuntimeError('Backup destination already exists; choose a new filename')
    for program in (pg_dump, pg_restore, fly):
        if not program.is_file():
            raise RuntimeError('Required local tool missing: '+str(program))
    for program in (pg_dump, pg_restore):
        version = subprocess.run([str(program), '--version'], capture_output=True, text=True, check=True).stdout
        if '(PostgreSQL) 17.' not in version:
            raise RuntimeError('Expected PostgreSQL 17 client tools')

    # The SSH command contains no credentials. Its captured stdout is never
    # forwarded to the terminal, logs, a file, or this program's error messages.
    remote = f'''import os,json
from urllib.parse import urlsplit,unquote
u=urlsplit(os.environ['DATABASE_URL'])
if (u.hostname,u.path.lstrip('/'),unquote(u.username or '')) != ({POOL!r},{DATABASE!r},{ROLE!r}):
 raise SystemExit('Production database target changed; inspect it before backing up')
print(json.dumps({{'password':unquote(u.password or '')}}))
'''
    connection = subprocess.run([str(fly), 'ssh', 'console', '-a', 'eigentask-api',
                                 '-C', 'python -c '+shlex.quote(remote)],
                                capture_output=True, text=True, timeout=90)
    if connection.returncode:
        raise RuntimeError('Could not retrieve the production credential through Fly; check Fly login and API machine availability')
    try:
        password = json.loads(connection.stdout)['password']
    except (ValueError, KeyError):
        raise RuntimeError('Unexpected credential response from Fly; no backup was started') from None
    if not password:
        raise RuntimeError('Production database password is missing')
    environment = {**os.environ, 'PGPASSWORD': password, 'PGSSLMODE': 'require',
                   'PGCHANNELBINDING': 'require', 'PGCONNECT_TIMEOUT': '30'}
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive binary creation prevents overwrites and PowerShell output
        # encoding cannot corrupt the archive. pg_dump writes binary stdout.
        with output.open('xb') as archive:
            result = subprocess.run(command(pg_dump), stdout=archive, stderr=subprocess.PIPE,
                                    env=environment, timeout=1800)
    finally:
        environment.pop('PGPASSWORD', None)
        password = None
        connection = None
    if result.returncode:
        raise RuntimeError('pg_dump failed; the output may be incomplete. Do not deploy or use that file as a backup')
    verification = subprocess.run([str(pg_restore), '--list', str(output)],
                                  capture_output=True, timeout=60)
    if verification.returncode:
        raise RuntimeError('pg_restore could not read the archive. Do not deploy')
    with output.open('rb') as archive:
        digest = hashlib.file_digest(archive, 'sha256').hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(digest+'  '+output.name+'\n', encoding='ascii')
    print('Backup created:', output)
    print('Bytes:', output.stat().st_size)
    print('Archive listing: verified with PostgreSQL 17 pg_restore --list (no restore performed)')
    print('SHA-256:', digest)
    print('No deployment or migrations were run.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        # Do not echo child-process output, connection strings or credentials.
        print('Backup stopped:', str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__, file=sys.stderr)
        sys.exit(1)
