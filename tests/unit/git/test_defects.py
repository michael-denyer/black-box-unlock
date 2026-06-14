"""Unit tests for bug-fix commit detection."""

from black_box_unlock.git.defects import bugfix_counts, is_bugfix_message
from tests.factories import make_commit


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

    def test_real_world_correcting_message(self):
        msg = "Messed up the condition here causing all Reps to lose actions menu in CSR. Correcting it here"
        assert is_bugfix_message(msg) is True

    def test_broken_pipeline(self):
        assert is_bugfix_message("broken pipeline after merge") is True

    def test_service_crash(self):
        assert is_bugfix_message("service crash on null kit") is True

    def test_repair_flaky_retry(self):
        assert is_bugfix_message("repair flaky retry") is True

    def test_feat_prefix_with_correct_stays_false(self):
        assert is_bugfix_message("feat: add correct rounding") is False

    def test_bare_correct_without_defect_verb_stays_false(self):
        assert is_bugfix_message("ensure correct behavior") is False

    def test_refactor_prefix_stays_false(self):
        assert is_bugfix_message("refactor: rename") is False

    def test_docs_prefix_stays_false(self):
        assert is_bugfix_message("docs: update readme") is False

    def test_fixing_inflection_detected(self):
        # the -ing form was missed by fix(es|ed)? - 9 real fixes in sampled repos
        assert is_bugfix_message("Fixing Mobile Menu Scroll Issue") is True

    def test_stuck_detected(self):
        assert is_bugfix_message("job stuck in retry queue") is True

    def test_hang_detected(self):
        assert is_bugfix_message("worker hangs on shutdown") is True

    def test_hung_detected(self):
        assert is_bugfix_message("connection left hung after deploy") is True

    def test_failure_word_is_not_bugfix(self):
        # 'fail'/'failure' deliberately excluded: high false-positive on real repos
        # (e.g. failure-handling features). Pin the decision against re-adding it.
        assert is_bugfix_message("track kit activation failure") is False

    def test_error_word_is_not_bugfix(self):
        # 'error' deliberately excluded: dominated by feature work ("add error handling")
        assert is_bugfix_message("add error handling for API timeouts") is False

    def test_hangfire_library_no_false_positive(self):
        # word boundary: "Hangfire" must not trip the hang/hung term
        assert is_bugfix_message("feat: schedule jobs with Hangfire") is False


class TestBugfixCounts:
    def test_counts_bugfix_commits_per_file(self):
        history = [
            make_commit(["src/auth.py", "src/user.py"], message="fix: auth crash"),
            make_commit(["src/user.py"], message="feat: add profile page"),
            make_commit(["src/auth.py"], message="hotfix: auth again"),
        ]

        counts = bugfix_counts(history)

        assert counts == {"src/auth.py": 2, "src/user.py": 1}

    def test_entries_without_message_are_skipped(self):
        history = [make_commit([], message="")]

        assert bugfix_counts(history) == {}
