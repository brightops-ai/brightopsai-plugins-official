"""Credential-shaped strings used to prove redaction actually fires.

These are invented, expired-by-construction samples that exist only so the
redaction tests assert against realistic input. They live under a fixtures
directory because secret scanners are supposed to flag strings shaped like
this -- that is the scanner working, not a finding.

Do not soften them into placeholders. A redaction test whose input no longer
looks like a credential proves nothing about redacting credentials.
"""

API_KEY = "sk-abcdefghijklmnopqrstuvwx"
GITHUB_TOKEN = "ghp_0123456789abcdefghij"
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
BEARER_HEADER = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz"
BEARER_VALUE = "abcdefghijklmnopqrstuvwxyz"
ASSIGNED_PASSWORD = "password=hunter2hunter2"
ASSIGNED_PASSWORD_VALUE = "hunter2hunter2"
CONNECTION_STRING = "postgres://someuser:somepass@db.internal/app"
CONNECTION_PASSWORD = "somepass"

PRIVATE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "secretbytes\n"
    "-----END OPENSSH PRIVATE KEY-----"
)
PRIVATE_KEY_BODY = "secretbytes"

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NX0.dBjftJeZ4CVPmB92K"
JWT_HEADER_SEGMENT = "eyJhbGciOiJIUzI1NiJ9"
