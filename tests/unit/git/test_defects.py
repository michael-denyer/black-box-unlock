"""Unit tests for bug-fix commit detection."""

from black_box_unlock.git.defects import bugfix_counts, is_bugfix_message


class TestIsBugfixMessage:
    def test_detects_fix_prefix(self):
        assert is_bugfix_message("fix: handle null token") is True

    def test_detects_fixes_issue_reference(self):
        assert is_bugfix_message("Fixes #142 race in retry loop") is True

    def test_detects_bug_word(self):
        assert is_bugfix_message("squash auth bug under load") is True

    def test_detects_revert(self):
        assert is_bugfix_message('Revert "feat: new cache layer"') is True

    def test_feature_commit_is_not_bugfix(self):
        assert is_bugfix_message("feat: add login page") is False

    def test_word_boundary_no_false_positive(self):
        # "prefix" contains "fix" but is not a bugfix marker
        assert is_bugfix_message("docs: explain url prefix handling") is False

    def test_docs_prefix_is_not_bugfix(self):
        assert is_bugfix_message("docs: fix stale architecture docs") is False

    def test_style_prefix_is_not_bugfix(self):
        assert is_bugfix_message("style(readme): fix line overlap") is False

    def test_test_prefix_is_not_bugfix(self):
        assert is_bugfix_message("test: fix flaky assertion") is False

    def test_scoped_fix_prefix_is_bugfix(self):
        assert is_bugfix_message("fix(core): validate empty input") is True

    def test_revert_of_docs_commit_still_counts(self):
        # a revert is a defect signal regardless of what it reverts
        assert is_bugfix_message('Revert "docs: add diagram"') is True


class TestBugfixCounts:
    def test_counts_bugfix_commits_per_file(self):
        history = {
            "entries": [
                {
                    "timestamp": "2026-01-20T10:00:00Z",
                    "author_email": "a@x.com",
                    "message": "fix: auth crash",
                    "files": [
                        {"path": "src/auth.py", "added_lines": 5, "deleted_lines": 1},
                        {"path": "src/user.py", "added_lines": 2, "deleted_lines": 0},
                    ],
                },
                {
                    "timestamp": "2026-01-21T10:00:00Z",
                    "author_email": "a@x.com",
                    "message": "feat: add profile page",
                    "files": [{"path": "src/user.py", "added_lines": 50, "deleted_lines": 0}],
                },
                {
                    "timestamp": "2026-01-22T10:00:00Z",
                    "author_email": "a@x.com",
                    "message": "hotfix: auth again",
                    "files": [{"path": "src/auth.py", "added_lines": 3, "deleted_lines": 3}],
                },
            ]
        }

        counts = bugfix_counts(history)

        assert counts == {"src/auth.py": 2, "src/user.py": 1}

    def test_entries_without_message_are_skipped(self):
        history = {
            "entries": [
                {"timestamp": "2026-01-20T10:00:00Z", "author_email": "a@x.com", "files": []}
            ]
        }

        assert bugfix_counts(history) == {}
