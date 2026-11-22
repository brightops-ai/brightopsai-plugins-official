# Changelog

All notable changes to this plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-21

### Added

- Baseline: released as 0.1.0. Ships two skills:
  - `restart`: pause the other busy threads, restart T3 Code with a detached
    script that runs an optional command while the app is closed, validate,
    and resume them.
  - `1password-secrets`: put a service account token in T3 Code's environment
    and sync `op://` references into its provider variables, with
    `t3_op_env_sync.py`, `op_token.sh` (token to keychain or `service.env`
    without argv) and a token-free `op_check.sh`.
