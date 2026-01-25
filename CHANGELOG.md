# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- File churn extraction from git history using gmap (BBU-8b03)
- Temporal coupling detection from git commits (BBU-f3v2)
- File ownership spread calculation (BBU-k4e2)
- Core data models: `FileChurn`, `TemporalCoupling`, `FileOwnership`
- Custom exceptions: `NotAGitRepoError`, `GitToolNotFoundError`
- Integration tests for git churn extraction
