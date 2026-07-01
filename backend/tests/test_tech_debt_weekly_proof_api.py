"""
Tech Debt & Weekly Proof API Tests
Tests for the 2 new endpoints:
- GET /api/ops/dashboard/tech-debt — Quarantine burn-down dashboard
- GET /api/ops/dashboard/channel-health/weekly-proof — Week-over-week improvement proof
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")


class TestTechDebtEndpoint:
    """Tests for GET /api/ops/dashboard/tech-debt — Quarantine burn-down dashboard"""

    def test_tech_debt_returns_200(self):
        """Test that tech-debt endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Tech debt endpoint returns 200")

    def test_tech_debt_response_structure(self):
        """Test that response contains all required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        assert response.status_code == 200
        data = response.json()

        required_fields = [
            "total_quarantined", "total_effort_hours", "total_weekly_target",
            "estimated_weeks_to_zero", "categories", "health_score",
            "health_grade", "calculated_at"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"PASS: All {len(required_fields)} required fields present")

    def test_tech_debt_total_quarantined_is_37(self):
        """Test that total_quarantined matches expected count from quarantine_manifest"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        data = response.json()
        
        # Based on quarantine_manifest.py: 10 stale_fixtures + 10 changed_api + 13 changed_implementation + 3 external_dependency + 1 meta-test = 37
        assert data["total_quarantined"] == 37, f"Expected 37 quarantined tests, got {data['total_quarantined']}"
        print(f"PASS: total_quarantined={data['total_quarantined']} matches expected 37")

    def test_tech_debt_has_5_categories(self):
        """Test that there are 5 categories as defined in QUARANTINE_CATEGORIES"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        data = response.json()
        
        categories = data.get("categories", [])
        assert len(categories) == 5, f"Expected 5 categories, got {len(categories)}"
        
        expected_keys = ["stale_fixtures", "changed_api", "changed_implementation", "external_dependency", "meta-test"]
        actual_keys = [c["key"] for c in categories]
        for key in expected_keys:
            assert key in actual_keys, f"Missing category: {key}"
        
        print(f"PASS: All 5 categories present: {actual_keys}")

    def test_tech_debt_category_structure(self):
        """Test that each category has required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        data = response.json()
        
        required_category_fields = [
            "key", "label", "description", "priority", "count",
            "effort_hours", "weekly_target", "weeks_to_clear", "tests"
        ]
        
        for cat in data.get("categories", []):
            for field in required_category_fields:
                assert field in cat, f"Missing field '{field}' in category '{cat.get('key', 'unknown')}'"
        
        print("PASS: All categories have required structure")

    def test_tech_debt_category_tests_structure(self):
        """Test that each test in a category has required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        data = response.json()
        
        required_test_fields = ["test_id", "full_path", "since", "reason"]
        
        for cat in data.get("categories", []):
            for test in cat.get("tests", []):
                for field in required_test_fields:
                    assert field in test, f"Missing field '{field}' in test of category '{cat['key']}'"
        
        print("PASS: All tests have required structure (test_id, full_path, since, reason)")

    def test_tech_debt_health_grade_is_valid(self):
        """Test that health_grade is A, B, C, or D"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        data = response.json()
        
        valid_grades = ["A", "B", "C", "D"]
        assert data["health_grade"] in valid_grades, f"Invalid health_grade: {data['health_grade']}"
        print(f"PASS: health_grade={data['health_grade']} is valid")

    def test_tech_debt_health_score_range(self):
        """Test that health_score is between 0 and 100"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        data = response.json()
        
        assert 0 <= data["health_score"] <= 100, f"health_score {data['health_score']} out of range [0, 100]"
        print(f"PASS: health_score={data['health_score']} is in valid range")

    def test_tech_debt_stale_fixtures_count(self):
        """Test that stale_fixtures category has 10 tests"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        data = response.json()
        
        stale_fixtures = next((c for c in data["categories"] if c["key"] == "stale_fixtures"), None)
        assert stale_fixtures is not None, "stale_fixtures category not found"
        assert stale_fixtures["count"] == 10, f"Expected 10 stale_fixtures tests, got {stale_fixtures['count']}"
        print(f"PASS: stale_fixtures has {stale_fixtures['count']} tests")

    def test_tech_debt_changed_api_count(self):
        """Test that changed_api category has 10 tests"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/tech-debt")
        data = response.json()
        
        changed_api = next((c for c in data["categories"] if c["key"] == "changed_api"), None)
        assert changed_api is not None, "changed_api category not found"
        assert changed_api["count"] == 10, f"Expected 10 changed_api tests, got {changed_api['count']}"
        print(f"PASS: changed_api has {changed_api['count']} tests")


class TestWeeklyProofEndpoint:
    """Tests for GET /api/ops/dashboard/channel-health/weekly-proof — Week-over-week improvement"""

    def test_weekly_proof_returns_200(self):
        """Test that weekly-proof endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Weekly proof endpoint returns 200")

    def test_weekly_proof_response_structure(self):
        """Test that response contains all required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof")
        assert response.status_code == 200
        data = response.json()

        required_fields = ["weeks", "improvements", "total_weeks", "calculated_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"PASS: All {len(required_fields)} required fields present")

    def test_weekly_proof_default_8_weeks(self):
        """Test that default weeks parameter returns 8 weeks"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof")
        data = response.json()
        
        assert data["total_weeks"] == 8, f"Expected 8 weeks by default, got {data['total_weeks']}"
        assert len(data["weeks"]) == 8, f"Expected 8 week entries, got {len(data['weeks'])}"
        print("PASS: Default returns 8 weeks of data")

    def test_weekly_proof_weeks_parameter(self):
        """Test weeks query parameter (2-52 range)"""
        for weeks in [4, 8, 12]:
            response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof?weeks={weeks}")
            assert response.status_code == 200, f"Expected 200 for weeks={weeks}"
            data = response.json()
            assert data["total_weeks"] == weeks, f"Expected {weeks} weeks, got {data['total_weeks']}"
        
        print("PASS: weeks parameter works correctly for 4, 8, 12")

    def test_weekly_proof_weeks_validation(self):
        """Test weeks parameter validation (min=2, max=52)"""
        # weeks=1 should fail (min is 2)
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof?weeks=1")
        assert response.status_code == 422, f"Expected 422 for weeks=1, got {response.status_code}"
        
        # weeks=53 should fail (max is 52)
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof?weeks=53")
        assert response.status_code == 422, f"Expected 422 for weeks=53, got {response.status_code}"
        
        print("PASS: weeks parameter validation works (rejects 1 and 53)")

    def test_weekly_proof_week_structure(self):
        """Test that each week entry has required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof")
        data = response.json()
        
        required_week_fields = [
            "week_label", "week_start", "week_end",
            "sync_success_rate", "drift_count", "mttr_hours",
            "sla_compliance", "push_latency_p95"
        ]
        
        for week in data.get("weeks", []):
            for field in required_week_fields:
                assert field in week, f"Missing field '{field}' in week entry"
        
        print("PASS: All week entries have required structure")

    def test_weekly_proof_improvements_structure(self):
        """Test that improvements object has delta fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof")
        data = response.json()
        
        improvements = data.get("improvements", {})
        required_improvement_fields = [
            "sync_success_delta", "drift_delta", "mttr_delta",
            "sla_delta", "push_p95_delta"
        ]
        
        for field in required_improvement_fields:
            assert field in improvements, f"Missing improvement field: {field}"
        
        print("PASS: improvements object has all delta fields")

    def test_weekly_proof_week_label_format(self):
        """Test that week_label follows W## format"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof")
        data = response.json()
        
        for week in data.get("weeks", []):
            label = week.get("week_label", "")
            assert label.startswith("W"), f"week_label should start with 'W', got: {label}"
            assert len(label) == 3, f"week_label should be 3 chars (W##), got: {label}"
        
        print("PASS: All week_labels follow W## format")

    def test_weekly_proof_date_format(self):
        """Test that week_start and week_end are YYYY-MM-DD format"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/weekly-proof")
        data = response.json()
        
        import re
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        
        for week in data.get("weeks", []):
            assert date_pattern.match(week["week_start"]), f"Invalid week_start format: {week['week_start']}"
            assert date_pattern.match(week["week_end"]), f"Invalid week_end format: {week['week_end']}"
        
        print("PASS: All dates follow YYYY-MM-DD format")


class TestCICDWorkflowFiles:
    """Tests to verify CI/CD workflow files have proper structure (YAML validation only)"""

    def test_cicd_yml_exists(self):
        """Test that ci-cd.yml exists"""
        import os
        cicd_path = "/app/.github/workflows/ci-cd.yml"
        assert os.path.exists(cicd_path), f"ci-cd.yml not found at {cicd_path}"
        print("PASS: ci-cd.yml exists")

    def test_deploy_yml_exists(self):
        """Test that deploy.yml exists"""
        import os
        deploy_path = "/app/.github/workflows/deploy.yml"
        assert os.path.exists(deploy_path), f"deploy.yml not found at {deploy_path}"
        print("PASS: deploy.yml exists")

    def test_cicd_yml_has_rollback_step(self):
        """Test that ci-cd.yml contains rollback logic"""
        with open("/app/.github/workflows/ci-cd.yml", "r") as f:
            content = f.read()
        
        assert "rollback" in content.lower(), "ci-cd.yml should contain rollback logic"
        assert "rollout undo" in content, "ci-cd.yml should contain 'rollout undo' command"
        print("PASS: ci-cd.yml contains rollback logic")

    def test_cicd_yml_has_smoke_test(self):
        """Test that ci-cd.yml contains smoke test step"""
        with open("/app/.github/workflows/ci-cd.yml", "r") as f:
            content = f.read()
        
        assert "smoke" in content.lower(), "ci-cd.yml should contain smoke test"
        assert "/api/health/" in content, "ci-cd.yml should test /api/health/ endpoint"
        print("PASS: ci-cd.yml contains smoke test")

    def test_cicd_yml_has_notification(self):
        """Test that ci-cd.yml contains notification step"""
        with open("/app/.github/workflows/ci-cd.yml", "r") as f:
            content = f.read()
        
        assert "notify" in content.lower() or "slack" in content.lower(), "ci-cd.yml should contain notification"
        assert "SLACK_DEPLOY_WEBHOOK" in content, "ci-cd.yml should reference SLACK_DEPLOY_WEBHOOK"
        print("PASS: ci-cd.yml contains notification step")

    def test_deploy_yml_has_rollback_step(self):
        """Test that deploy.yml contains rollback logic"""
        with open("/app/.github/workflows/deploy.yml", "r") as f:
            content = f.read()
        
        assert "rollback" in content.lower(), "deploy.yml should contain rollback logic"
        assert "rollout undo" in content, "deploy.yml should contain 'rollout undo' command"
        print("PASS: deploy.yml contains rollback logic")

    def test_deploy_yml_has_db_backup(self):
        """Test that deploy.yml contains DB backup step for production"""
        with open("/app/.github/workflows/deploy.yml", "r") as f:
            content = f.read()
        
        assert "backup" in content.lower(), "deploy.yml should contain backup step"
        assert "MONGO_BACKUP_URI" in content, "deploy.yml should reference MONGO_BACKUP_URI"
        print("PASS: deploy.yml contains DB backup step")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
