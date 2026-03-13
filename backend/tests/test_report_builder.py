"""
Report Builder API Tests - Faz 4
Tests for custom report builder functionality including:
- Config endpoint with 6 data sources
- Report generation with selected columns
- Excel/PDF export
- Template CRUD operations
- Date presets and advanced filters
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestReportBuilderConfig:
    """Report Builder configuration endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # Note: Token field is 'access_token' not 'token'
        self.token = data.get("access_token")
        assert self.token, "No access_token in response"
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_config_returns_six_data_sources(self):
        """Verify config endpoint returns exactly 6 data sources"""
        response = requests.get(
            f"{BASE_URL}/api/reports/builder/config",
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "data_sources" in data
        
        # Verify 6 data sources exist
        sources = data["data_sources"]
        expected_sources = ["reservations", "revenue", "guests", "rooms", "housekeeping", "folios"]
        
        for source in expected_sources:
            assert source in sources, f"Missing data source: {source}"
        
        assert len(sources) == 6, f"Expected 6 data sources, got {len(sources)}"
        print(f"✓ Config returns all 6 data sources: {list(sources.keys())}")
    
    def test_each_source_has_columns(self):
        """Verify each data source has columns defined"""
        response = requests.get(
            f"{BASE_URL}/api/reports/builder/config",
            headers=self.headers
        )
        assert response.status_code == 200
        
        sources = response.json()["data_sources"]
        
        for source_key, source_data in sources.items():
            assert "label" in source_data, f"{source_key} missing label"
            assert "columns" in source_data, f"{source_key} missing columns"
            assert len(source_data["columns"]) > 0, f"{source_key} has no columns"
            print(f"✓ {source_key}: {len(source_data['columns'])} columns")
    
    def test_column_definitions_structure(self):
        """Verify column definitions have required fields"""
        response = requests.get(
            f"{BASE_URL}/api/reports/builder/config",
            headers=self.headers
        )
        assert response.status_code == 200
        
        sources = response.json()["data_sources"]
        
        # Check reservations columns as sample
        reservations = sources["reservations"]["columns"]
        for col_key, col_data in reservations.items():
            assert "label" in col_data, f"Column {col_key} missing label"
            assert "type" in col_data, f"Column {col_key} missing type"
        
        print("✓ Column definitions have required structure")


class TestReportGeneration:
    """Report generation endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        self.token = data.get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_generate_reservations_report(self):
        """Test generating a reservations report with selected columns"""
        config = {
            "data_source": "reservations",
            "columns": ["guest_name", "room_number", "check_in", "check_out", "status", "total_amount"],
            "filters": [],
            "date_from": None,
            "date_to": None,
            "sort_by": None,
            "sort_order": "desc",
            "limit": 100
        }
        
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/generate",
            headers=self.headers,
            json=config
        )
        assert response.status_code == 200, f"Generate failed: {response.text}"
        
        result = response.json()
        assert "data" in result
        assert "total_count" in result
        assert "column_labels" in result
        assert "generated_at" in result
        
        print(f"✓ Report generated with {result['total_count']} records")
    
    def test_generate_revenue_report(self):
        """Test generating a revenue report"""
        config = {
            "data_source": "revenue",
            "columns": ["description", "amount", "charge_type", "date"],
            "filters": [],
            "limit": 50
        }
        
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/generate",
            headers=self.headers,
            json=config
        )
        assert response.status_code == 200
        
        result = response.json()
        assert "data" in result
        print(f"✓ Revenue report generated with {result['total_count']} records")
    
    def test_generate_rooms_report(self):
        """Test generating a rooms report"""
        config = {
            "data_source": "rooms",
            "columns": ["number", "type", "floor", "status", "base_rate"],
            "filters": [],
            "limit": 100
        }
        
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/generate",
            headers=self.headers,
            json=config
        )
        assert response.status_code == 200
        
        result = response.json()
        assert "data" in result
        print(f"✓ Rooms report generated with {result['total_count']} records")
    
    def test_generate_with_date_filter(self):
        """Test report generation with date range filter"""
        today = datetime.now()
        last_90_days = (today - timedelta(days=90)).strftime("%Y-%m-%d")
        today_str = today.strftime("%Y-%m-%d")
        
        config = {
            "data_source": "reservations",
            "columns": ["guest_name", "check_in", "total_amount"],
            "filters": [],
            "date_from": last_90_days,
            "date_to": today_str,
            "limit": 100
        }
        
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/generate",
            headers=self.headers,
            json=config
        )
        assert response.status_code == 200
        
        result = response.json()
        print(f"✓ Report with date filter generated: {result['total_count']} records")
    
    def test_generate_with_advanced_filter(self):
        """Test report generation with advanced filters"""
        config = {
            "data_source": "reservations",
            "columns": ["guest_name", "status", "total_amount"],
            "filters": [
                {"field": "status", "operator": "eq", "value": "confirmed"}
            ],
            "limit": 100
        }
        
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/generate",
            headers=self.headers,
            json=config
        )
        assert response.status_code == 200
        
        result = response.json()
        print(f"✓ Report with advanced filter generated: {result['total_count']} records")
    
    def test_generate_summary_stats(self):
        """Test that numeric columns get summary statistics"""
        config = {
            "data_source": "reservations",
            "columns": ["guest_name", "total_amount", "nights"],
            "filters": [],
            "limit": 100
        }
        
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/generate",
            headers=self.headers,
            json=config
        )
        assert response.status_code == 200
        
        result = response.json()
        # Summary should exist for numeric columns if data exists
        assert "summary" in result
        print(f"✓ Summary stats returned: {list(result.get('summary', {}).keys())}")


class TestReportExport:
    """Report export endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        self.token = data.get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_export_excel(self):
        """Test Excel export functionality"""
        config = {
            "data_source": "reservations",
            "columns": ["guest_name", "room_number", "check_in", "total_amount"],
            "filters": [],
            "limit": 100
        }
        
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/export/excel",
            headers=self.headers,
            json=config
        )
        assert response.status_code == 200, f"Excel export failed: {response.text}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "spreadsheetml" in content_type or "octet-stream" in content_type, f"Unexpected content type: {content_type}"
        
        # Check content-disposition header for filename
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert ".xlsx" in content_disp
        
        # Check file has content
        assert len(response.content) > 0
        print(f"✓ Excel export successful: {len(response.content)} bytes")
    
    def test_export_pdf(self):
        """Test PDF export functionality"""
        config = {
            "data_source": "rooms",
            "columns": ["number", "type", "status", "base_rate"],
            "filters": [],
            "limit": 50
        }
        
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/export/pdf",
            headers=self.headers,
            json=config
        )
        assert response.status_code == 200, f"PDF export failed: {response.text}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "pdf" in content_type or "octet-stream" in content_type, f"Unexpected content type: {content_type}"
        
        # Check content-disposition header for filename
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert ".pdf" in content_disp
        
        # Check file has content
        assert len(response.content) > 0
        print(f"✓ PDF export successful: {len(response.content)} bytes")


class TestReportTemplates:
    """Report template CRUD tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        self.token = data.get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        self.created_template_ids = []
    
    def teardown_method(self):
        """Clean up created templates"""
        for template_id in self.created_template_ids:
            try:
                requests.delete(
                    f"{BASE_URL}/api/reports/builder/templates/{template_id}",
                    headers=self.headers
                )
            except Exception:
                pass
    
    def test_list_templates(self):
        """Test listing saved templates"""
        response = requests.get(
            f"{BASE_URL}/api/reports/builder/templates",
            headers=self.headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "templates" in data
        print(f"✓ Templates list returned: {len(data['templates'])} templates")
    
    def test_save_template(self):
        """Test saving a new template"""
        template_name = f"TEST_template_{uuid.uuid4().hex[:8]}"
        template_data = {
            "name": template_name,
            "description": "Test template for automated testing",
            "config": {
                "data_source": "reservations",
                "columns": ["guest_name", "check_in", "total_amount"],
                "filters": [],
                "date_from": None,
                "date_to": None,
                "sort_by": None,
                "sort_order": "desc",
                "limit": 100
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/templates",
            headers=self.headers,
            json=template_data
        )
        assert response.status_code == 200, f"Save template failed: {response.text}"
        
        result = response.json()
        assert "id" in result
        assert result["name"] == template_name
        
        # Track for cleanup
        self.created_template_ids.append(result["id"])
        
        print(f"✓ Template saved: {result['name']} (id: {result['id']})")
        return result["id"]
    
    def test_save_and_verify_template(self):
        """Test saving a template and verifying it appears in list"""
        # Save template
        template_name = f"TEST_verify_{uuid.uuid4().hex[:8]}"
        template_data = {
            "name": template_name,
            "config": {
                "data_source": "revenue",
                "columns": ["amount", "charge_type"],
                "filters": [],
                "limit": 50
            }
        }
        
        save_response = requests.post(
            f"{BASE_URL}/api/reports/builder/templates",
            headers=self.headers,
            json=template_data
        )
        assert save_response.status_code == 200
        
        saved_template = save_response.json()
        self.created_template_ids.append(saved_template["id"])
        
        # Verify in list
        list_response = requests.get(
            f"{BASE_URL}/api/reports/builder/templates",
            headers=self.headers
        )
        assert list_response.status_code == 200
        
        templates = list_response.json()["templates"]
        found = any(t["id"] == saved_template["id"] for t in templates)
        assert found, "Saved template not found in list"
        
        print("✓ Template saved and verified in list")
    
    def test_delete_template(self):
        """Test deleting a template"""
        # First create a template
        template_name = f"TEST_delete_{uuid.uuid4().hex[:8]}"
        template_data = {
            "name": template_name,
            "config": {
                "data_source": "guests",
                "columns": ["name", "email"],
                "filters": [],
                "limit": 100
            }
        }
        
        save_response = requests.post(
            f"{BASE_URL}/api/reports/builder/templates",
            headers=self.headers,
            json=template_data
        )
        assert save_response.status_code == 200
        template_id = save_response.json()["id"]
        
        # Delete the template
        delete_response = requests.delete(
            f"{BASE_URL}/api/reports/builder/templates/{template_id}",
            headers=self.headers
        )
        assert delete_response.status_code == 200
        
        # Verify deletion
        list_response = requests.get(
            f"{BASE_URL}/api/reports/builder/templates",
            headers=self.headers
        )
        templates = list_response.json()["templates"]
        found = any(t["id"] == template_id for t in templates)
        assert not found, "Deleted template still appears in list"
        
        print("✓ Template deleted and verified removal")
    
    def test_delete_nonexistent_template(self):
        """Test deleting a non-existent template returns 404"""
        fake_id = str(uuid.uuid4())
        
        response = requests.delete(
            f"{BASE_URL}/api/reports/builder/templates/{fake_id}",
            headers=self.headers
        )
        assert response.status_code == 404
        print("✓ Delete non-existent template returns 404")


class TestReportBuilderAuth:
    """Authentication tests for Report Builder"""
    
    def test_config_requires_auth(self):
        """Test that config endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/reports/builder/config")
        assert response.status_code in [401, 403, 422]
        print("✓ Config endpoint requires authentication")
    
    def test_generate_requires_auth(self):
        """Test that generate endpoint requires authentication"""
        config = {
            "data_source": "reservations",
            "columns": ["guest_name"],
            "filters": [],
            "limit": 10
        }
        response = requests.post(
            f"{BASE_URL}/api/reports/builder/generate",
            json=config
        )
        assert response.status_code in [401, 403, 422]
        print("✓ Generate endpoint requires authentication")
    
    def test_templates_requires_auth(self):
        """Test that templates endpoint requires authentication"""
        response = requests.get(f"{BASE_URL}/api/reports/builder/templates")
        assert response.status_code in [401, 403, 422]
        print("✓ Templates endpoint requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
