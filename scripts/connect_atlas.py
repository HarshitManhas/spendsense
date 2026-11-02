"""Verify a private Atlas candidate, then optionally switch the app configuration."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import uuid
from urllib.parse import parse_qs, quote, urlsplit

from dotenv import dotenv_values, set_key
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]


def validate_candidate(values):
    uri = values.get('MONGODB_URI') or ''
    if '<db_password>' in uri and values.get('ATLAS_PASSWORD'):
        uri = uri.replace('<db_password>', quote(values['ATLAS_PASSWORD'], safe=''))
    name = values.get('MONGODB_DATABASE') or 'spendsense'
    parsed = urlsplit(uri)
    if parsed.scheme != 'mongodb+srv' or not (parsed.hostname or '').endswith('.mongodb.net'):
        raise ValueError('Use the mongodb+srv connection string from Atlas Connect > Drivers.')
    if not parsed.username or not parsed.password or '<' in uri or '>' in uri:
        raise ValueError('Complete the database username/password in the private candidate file.')
    params = {k.casefold(): v[-1].casefold() for k, v in parse_qs(parsed.query).items()}
    if any(params.get(k) == 'false' for k in ('tls', 'ssl')) or any(
        params.get(k) == 'true' for k in ('tlsinsecure', 'tlsallowinvalidcertificates', 'tlsallowinvalidhostnames')):
        raise ValueError('Keep TLS and certificate verification enabled for Atlas.')
    if not name or any(c in name for c in '/\\. "$*<>:|?\x00'):
        raise ValueError('Use a valid application database name, such as spendsense.')
    return uri, name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=ROOT / '.env.atlas')
    parser.add_argument('--apply', action='store_true', help='Update .env only after the connection and write probe pass')
    args = parser.parse_args()
    active = ROOT / '.env'
    if args.candidate.resolve() == active.resolve():
        parser.error('Use a separate candidate file so a failed connection cannot replace the working configuration.')
    try:
        uri, name = validate_candidate(dotenv_values(args.candidate, interpolate=False))
    except ValueError as exc:
        parser.error(str(exc))
    try:
        with MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000,
                         socketTimeoutMS=10000, appname='SpendSense-setup') as client:
            client.admin.command('ping')
            check = client[name]['_connection_checks']
            check.create_index('expiresAt', expireAfterSeconds=0)
            probe_id = 'setup-' + uuid.uuid4().hex
            check.insert_one({'_id': probe_id, 'purpose': 'SpendSense connection test',
                              'expiresAt': datetime.now(timezone.utc) + timedelta(minutes=30)})
            try:
                if check.find_one({'_id': probe_id}) is None:
                    raise RuntimeError('Read-back failed')
            finally:
                check.delete_one({'_id': probe_id})
    except Exception as exc:
        # Driver errors can contain the connection URI. Never print raw errors.
        raise SystemExit(f'Atlas verification failed ({type(exc).__name__}). Check credentials, cluster status, DNS and the IP access list. Active .env was not changed.') from None
    print('Atlas ping, index creation, write, read-back and probe cleanup passed.')
    if args.apply:
        backup = ROOT / '.env.before-atlas'
        if active.exists() and not backup.exists():
            shutil.copyfile(active, backup)
        temporary = ROOT / '.env.atlas-apply.tmp'
        temporary.write_text(active.read_text(encoding='utf-8') if active.exists() else '', encoding='utf-8')
        try:
            set_key(temporary, 'MONGODB_URI', uri)
            set_key(temporary, 'MONGODB_DATABASE', name)
            temporary.replace(active)
        finally:
            temporary.unlink(missing_ok=True)
        print('Updated .env. Restart the API and worker. Existing local data has not been migrated.')
    else:
        print('Check only: the app still uses its existing configuration. Use --apply to switch.')


if __name__ == '__main__':
    main()
