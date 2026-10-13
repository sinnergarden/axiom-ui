"""Local password provisioning and bounded in-memory login sessions."""
from collections import deque
from getpass import getpass
from hashlib import pbkdf2_hmac
from hmac import compare_digest
import argparse
import json
import os
from pathlib import Path
import secrets
from threading import Lock
from time import monotonic

ITERATIONS = 600_000


def password_record(password):
    if not isinstance(password, str) or not 6 <= len(password) <= 128:
        raise ValueError('password must contain 6 to 128 characters')
    salt = secrets.token_bytes(16)
    return dict(version=1, salt=salt.hex(), iterations=ITERATIONS,
                verifier=pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS).hex())


class PasswordLogin:
    def __init__(self, record):
        if (set(record) != {'version', 'salt', 'iterations', 'verifier'} or
                record['version'] != 1 or record['iterations'] != ITERATIONS or
                len(bytes.fromhex(record['salt'])) != 16 or
                len(bytes.fromhex(record['verifier'])) != 32):
            raise ValueError('invalid password record')
        self.record = record
        self.failures, self.sessions = deque(), {}
        self.lock = Lock()

    def login(self, password):
        # Global bound intentionally also protects a service behind a loopback
        # reverse proxy; untrusted forwarded IP headers cannot bypass it.
        with self.lock:
            now = monotonic()
            while self.failures and self.failures[0] <= now - 60:
                self.failures.popleft()
            if len(self.failures) >= 5:
                return 429, None
            valid = False
            if isinstance(password, str) and 6 <= len(password) <= 128:
                hashed = pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(self.record['salt']), ITERATIONS)
                valid = compare_digest(hashed, bytes.fromhex(self.record['verifier']))
            if not valid:
                self.failures.append(now)
                return 401, None
            self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
            if len(self.sessions) >= 64:
                self.sessions.pop(next(iter(self.sessions)))
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now + 12 * 60 * 60
            return 200, token

    def authorized(self, token):
        with self.lock:
            return self.sessions.get(token, 0) > monotonic()

    def logout(self, token):
        with self.lock:
            self.sessions.pop(token, None)


def main():
    parser = argparse.ArgumentParser(description='Set a private Mac results password locally')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Exclusive creation avoids silently replacing any existing credential.
    if args.output.exists():
        parser.exit(2, 'Output already exists; choose a new private file.\n')
    first = getpass('New results password (6–128 characters): ')
    second = getpass('Repeat password: ')
    if first != second:
        parser.exit(2, 'Passwords differ; no file written.\n')
    try:
        record = password_record(first)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(record, stream)
    except (ValueError, OSError):
        parser.exit(2, 'Cannot save: check password length and private output location.\n')
    print('Password verifier saved. Start the reviewed service with --password-file and this path.')


if __name__ == '__main__':
    main()
