"""Integration tests for git churn extraction."""

from black_box_unlock.git.churn import extract_file_churn


class TestExtractFileChurnIntegration:
    """Integration tests using real git repository."""

    def test_extracts_churn_from_this_repo(self, repo_root):
        """Extracts file churn from the black-box-unlock repository."""
        result = extract_file_churn(repo_root, since_days=30)

        assert len(result) > 0
        for churn in result:
            assert churn.path
            assert churn.commits >= 1
            assert churn.lines_added >= 0
            assert churn.lines_deleted >= 0

    def test_results_sortable_by_churn(self, repo_root):
        """Results can be sorted by total lines changed."""
        result = extract_file_churn(repo_root, since_days=30)
        sorted_result = sorted(result, key=lambda x: x.total_lines_changed, reverse=True)

        if len(sorted_result) > 1:
            assert sorted_result[0].total_lines_changed >= sorted_result[1].total_lines_changed
