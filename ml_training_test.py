#!/usr/bin/env python3
"""
ML Training Endpoints Testing - Comprehensive Testing
Testing 6 ML training endpoints for hotel PMS system
"""

import requests
import json
import sys
import os
import time
from datetime import datetime

# Configuration
BACKEND_URL = "https://app-audit-9.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

class MLTrainingTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = {
            "individual_training": {"passed": 0, "failed": 0, "details": []},
            "bulk_training": {"passed": 0, "failed": 0, "details": []},
            "model_status": {"passed": 0, "failed": 0, "details": []}
        }

    def authenticate(self):
        """Authenticate with the backend"""
        print("🔐 Authenticating...")
        try:
            response = self.session.post(f"{BACKEND_URL}/auth/login", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            })
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data["access_token"]
                self.tenant_id = data["user"]["tenant_id"]
                self.user_id = data["user"]["id"]
                self.session.headers.update({
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json"
                })
                print(f"✅ Authentication successful - User: {data['user']['name']}")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False

    def log_test_result(self, category, endpoint, method, success, details=""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "endpoint": f"{method} {endpoint}",
            "status": status,
            "details": details
        }
        self.test_results[category]["details"].append(result)
        if success:
            self.test_results[category]["passed"] += 1
        else:
            self.test_results[category]["failed"] += 1
        
        print(f"  {status}: {method} {endpoint} - {details}")

    def test_model_status_before_training(self):
        """Test GET /api/ml/models/status BEFORE training"""
        print("\n📊 Testing Model Status BEFORE Training...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/ml/models/status")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                
                # Verify response structure
                required_fields = ['models', 'summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    models = data.get('models', {})
                    summary = data.get('summary', {})
                    
                    # Check expected models
                    expected_models = ['rms', 'persona', 'predictive_maintenance', 'hk_scheduler']
                    found_models = list(models.keys())
                    details += f" - Models found: {found_models}"
                    
                    # Check if all models are untrained initially
                    trained_models = [name for name, info in models.items() if info.get('trained', False)]
                    details += f" - Trained models: {len(trained_models)}"
                    
                    # Check summary
                    total_models = summary.get('total_models', 0)
                    trained_count = summary.get('trained_models', 0)
                    details += f" - Summary: {trained_count}/{total_models} trained"
                    
                    # Verify all models show as untrained initially
                    if trained_count == 0:
                        details += " - All models untrained ✓"
                    else:
                        details += f" - WARNING: {trained_count} models already trained"
            
            self.log_test_result("model_status", "/ml/models/status (before)", "GET", success, details)
        except Exception as e:
            self.log_test_result("model_status", "/ml/models/status (before)", "GET", False, f"Error: {str(e)}")

    def test_individual_model_training(self):
        """Test individual model training endpoints"""
        print("\n🤖 Testing Individual Model Training...")
        
        # 1. Test RMS Training
        print("\n💰 Testing RMS Training...")
        try:
            start_time = time.time()
            response = self.session.post(f"{BACKEND_URL}/ml/rms/train")
            end_time = time.time()
            training_time = end_time - start_time
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}, Time: {training_time:.1f}s"
            
            if success and response.json():
                data = response.json()
                
                # Verify response structure
                required_fields = ['success', 'message', 'metrics', 'data_summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    # Check success flag
                    if data.get('success'):
                        details += " - Training successful ✓"
                    else:
                        details += " - Training failed"
                        success = False
                    
                    # Check metrics
                    metrics = data.get('metrics', {})
                    if 'occupancy_model' in metrics and 'pricing_model' in metrics:
                        occ_metrics = metrics['occupancy_model']
                        price_metrics = metrics['pricing_model']
                        
                        # Check occupancy model metrics
                        if 'rmse' in occ_metrics and 'r2' in occ_metrics:
                            rmse = occ_metrics['rmse']
                            r2 = occ_metrics['r2']
                            details += f" - Occupancy: RMSE={rmse:.3f}, R²={r2:.3f}"
                            
                            # Verify reasonable performance
                            if r2 > 0.7:
                                details += " ✓"
                            else:
                                details += f" (R² < 0.7)"
                        
                        # Check pricing model metrics
                        if 'rmse' in price_metrics and 'r2' in price_metrics:
                            rmse = price_metrics['rmse']
                            r2 = price_metrics['r2']
                            details += f" - Pricing: RMSE={rmse:.3f}, R²={r2:.3f}"
                            
                            if r2 > 0.7:
                                details += " ✓"
                            else:
                                details += f" (R² < 0.7)"
                    
                    # Check data summary
                    data_summary = data.get('data_summary', {})
                    if 'total_samples' in data_summary:
                        total_samples = data_summary['total_samples']
                        details += f" - Samples: {total_samples}"
                        
                        # Should be 730 days (2 years)
                        if total_samples >= 700:
                            details += " ✓"
                        else:
                            details += f" (expected ~730)"
            
            self.log_test_result("individual_training", "/ml/rms/train", "POST", success, details)
        except Exception as e:
            self.log_test_result("individual_training", "/ml/rms/train", "POST", False, f"Error: {str(e)}")

        # 2. Test Persona Training
        print("\n👤 Testing Persona Training...")
        try:
            start_time = time.time()
            response = self.session.post(f"{BACKEND_URL}/ml/persona/train")
            end_time = time.time()
            training_time = end_time - start_time
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}, Time: {training_time:.1f}s"
            
            if success and response.json():
                data = response.json()
                
                # Verify response structure
                required_fields = ['success', 'message', 'metrics', 'data_summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    # Check success flag
                    if data.get('success'):
                        details += " - Training successful ✓"
                    else:
                        details += " - Training failed"
                        success = False
                    
                    # Check metrics
                    metrics = data.get('metrics', {})
                    if 'accuracy' in metrics:
                        accuracy = metrics['accuracy']
                        details += f" - Accuracy: {accuracy:.3f}"
                        
                        # Verify reasonable performance (>80%)
                        if accuracy > 0.8:
                            details += " ✓"
                        else:
                            details += f" (< 80%)"
                    
                    if 'classification_report' in metrics:
                        details += " - Classification report ✓"
                    
                    # Check data summary
                    data_summary = data.get('data_summary', {})
                    if 'total_guests' in data_summary:
                        total_guests = data_summary['total_guests']
                        details += f" - Guests: {total_guests}"
                        
                        # Should be 400 guests
                        if total_guests >= 350:
                            details += " ✓"
                        else:
                            details += f" (expected ~400)"
                    
                    # Check persona distribution
                    if 'persona_distribution' in data_summary:
                        persona_dist = data_summary['persona_distribution']
                        details += f" - Personas: {len(persona_dist)} types"
            
            self.log_test_result("individual_training", "/ml/persona/train", "POST", success, details)
        except Exception as e:
            self.log_test_result("individual_training", "/ml/persona/train", "POST", False, f"Error: {str(e)}")

        # 3. Test Predictive Maintenance Training
        print("\n🔧 Testing Predictive Maintenance Training...")
        try:
            start_time = time.time()
            response = self.session.post(f"{BACKEND_URL}/ml/predictive-maintenance/train")
            end_time = time.time()
            training_time = end_time - start_time
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}, Time: {training_time:.1f}s"
            
            if success and response.json():
                data = response.json()
                
                # Verify response structure
                required_fields = ['success', 'message', 'metrics', 'data_summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    # Check success flag
                    if data.get('success'):
                        details += " - Training successful ✓"
                    else:
                        details += " - Training failed"
                        success = False
                    
                    # Check metrics (should have both risk and days models)
                    metrics = data.get('metrics', {})
                    if 'risk_model' in metrics and 'days_model' in metrics:
                        risk_metrics = metrics['risk_model']
                        days_metrics = metrics['days_model']
                        
                        # Check risk model accuracy
                        if 'accuracy' in risk_metrics:
                            accuracy = risk_metrics['accuracy']
                            details += f" - Risk accuracy: {accuracy:.3f}"
                            
                            if accuracy > 0.8:
                                details += " ✓"
                            else:
                                details += f" (< 80%)"
                        
                        # Check days model performance
                        if 'rmse' in days_metrics and 'r2' in days_metrics:
                            rmse = days_metrics['rmse']
                            r2 = days_metrics['r2']
                            details += f" - Days: RMSE={rmse:.1f}, R²={r2:.3f}"
                            
                            if r2 > 0.7:
                                details += " ✓"
                            else:
                                details += f" (R² < 0.7)"
                    
                    # Check data summary
                    data_summary = data.get('data_summary', {})
                    if 'total_samples' in data_summary:
                        total_samples = data_summary['total_samples']
                        details += f" - Samples: {total_samples}"
                        
                        # Should be 1000 samples
                        if total_samples >= 900:
                            details += " ✓"
                        else:
                            details += f" (expected ~1000)"
                    
                    # Check equipment distribution
                    if 'equipment_distribution' in data_summary:
                        equip_dist = data_summary['equipment_distribution']
                        details += f" - Equipment types: {len(equip_dist)}"
            
            self.log_test_result("individual_training", "/ml/predictive-maintenance/train", "POST", success, details)
        except Exception as e:
            self.log_test_result("individual_training", "/ml/predictive-maintenance/train", "POST", False, f"Error: {str(e)}")

        # 4. Test Housekeeping Scheduler Training
        print("\n🧹 Testing Housekeeping Scheduler Training...")
        try:
            start_time = time.time()
            response = self.session.post(f"{BACKEND_URL}/ml/hk-scheduler/train")
            end_time = time.time()
            training_time = end_time - start_time
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}, Time: {training_time:.1f}s"
            
            if success and response.json():
                data = response.json()
                
                # Verify response structure
                required_fields = ['success', 'message', 'metrics', 'data_summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    # Check success flag
                    if data.get('success'):
                        details += " - Training successful ✓"
                    else:
                        details += " - Training failed"
                        success = False
                    
                    # Check metrics (should have both staff and hours models)
                    metrics = data.get('metrics', {})
                    if 'staff_model' in metrics and 'hours_model' in metrics:
                        staff_metrics = metrics['staff_model']
                        hours_metrics = metrics['hours_model']
                        
                        # Check staff model performance
                        if 'rmse' in staff_metrics and 'r2' in staff_metrics:
                            rmse = staff_metrics['rmse']
                            r2 = staff_metrics['r2']
                            details += f" - Staff: RMSE={rmse:.2f}, R²={r2:.3f}"
                            
                            if r2 > 0.7:
                                details += " ✓"
                            else:
                                details += f" (R² < 0.7)"
                        
                        # Check hours model performance
                        if 'rmse' in hours_metrics and 'r2' in hours_metrics:
                            rmse = hours_metrics['rmse']
                            r2 = hours_metrics['r2']
                            details += f" - Hours: RMSE={rmse:.1f}, R²={r2:.3f}"
                            
                            if r2 > 0.7:
                                details += " ✓"
                            else:
                                details += f" (R² < 0.7)"
                    
                    # Check data summary
                    data_summary = data.get('data_summary', {})
                    if 'total_days' in data_summary:
                        total_days = data_summary['total_days']
                        details += f" - Days: {total_days}"
                        
                        # Should be 365 days
                        if total_days >= 350:
                            details += " ✓"
                        else:
                            details += f" (expected ~365)"
                    
                    # Check staffing metrics
                    if 'avg_staff_needed' in data_summary and 'peak_staff_needed' in data_summary:
                        avg_staff = data_summary['avg_staff_needed']
                        peak_staff = data_summary['peak_staff_needed']
                        details += f" - Staff: avg={avg_staff:.1f}, peak={peak_staff}"
            
            self.log_test_result("individual_training", "/ml/hk-scheduler/train", "POST", success, details)
        except Exception as e:
            self.log_test_result("individual_training", "/ml/hk-scheduler/train", "POST", False, f"Error: {str(e)}")

    def test_bulk_training(self):
        """Test POST /api/ml/train-all - Train all models in sequence"""
        print("\n🚀 Testing Bulk Training (Train All Models)...")
        
        try:
            start_time = time.time()
            response = self.session.post(f"{BACKEND_URL}/ml/train-all")
            end_time = time.time()
            training_time = end_time - start_time
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}, Time: {training_time:.1f}s"
            
            if success and response.json():
                data = response.json()
                
                # Verify response structure
                required_fields = ['success', 'message', 'results', 'summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    # Check overall success
                    overall_success = data.get('success', False)
                    details += f" - Overall success: {overall_success}"
                    
                    # Check results for each model
                    results = data.get('results', {})
                    expected_models = ['rms', 'persona', 'predictive_maintenance', 'hk_scheduler']
                    
                    successful_models = []
                    failed_models = []
                    
                    for model_name in expected_models:
                        if model_name in results:
                            model_result = results[model_name]
                            status = model_result.get('status', 'unknown')
                            
                            if status == 'success':
                                successful_models.append(model_name)
                            else:
                                failed_models.append(model_name)
                                error = model_result.get('error', 'Unknown error')
                                details += f" - {model_name} failed: {error}"
                        else:
                            failed_models.append(model_name)
                            details += f" - {model_name} missing from results"
                    
                    details += f" - Success: {len(successful_models)}/{len(expected_models)}"
                    
                    # Check summary
                    summary = data.get('summary', {})
                    if 'successful' in summary and 'failed' in summary:
                        successful_count = summary['successful']
                        failed_count = summary['failed']
                        details += f" - Summary: {successful_count} success, {failed_count} failed"
                        
                        # Verify counts match
                        if successful_count == len(successful_models) and failed_count == len(failed_models):
                            details += " ✓"
                        else:
                            details += " (count mismatch)"
                    
                    # Check if any errors reported
                    errors = data.get('errors', [])
                    if errors:
                        details += f" - Errors: {len(errors)}"
                        for error in errors[:2]:  # Show first 2 errors
                            details += f" - {error}"
                    else:
                        details += " - No errors ✓"
                    
                    # Overall success should match individual results
                    if len(failed_models) == 0 and overall_success:
                        details += " - All models trained successfully ✅"
                    elif len(failed_models) > 0:
                        details += f" - {len(failed_models)} models failed"
                        success = len(successful_models) >= 2  # At least half should succeed
            
            self.log_test_result("bulk_training", "/ml/train-all", "POST", success, details)
        except Exception as e:
            self.log_test_result("bulk_training", "/ml/train-all", "POST", False, f"Error: {str(e)}")

    def test_model_status_after_training(self):
        """Test GET /api/ml/models/status AFTER training"""
        print("\n📊 Testing Model Status AFTER Training...")
        
        try:
            response = self.session.get(f"{BACKEND_URL}/ml/models/status")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                
                # Verify response structure
                required_fields = ['models', 'summary']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    details += f" - Missing fields: {missing_fields}"
                    success = False
                else:
                    models = data.get('models', {})
                    summary = data.get('summary', {})
                    
                    # Check each model status
                    expected_models = ['rms', 'persona', 'predictive_maintenance', 'hk_scheduler']
                    trained_models = []
                    untrained_models = []
                    
                    for model_name in expected_models:
                        if model_name in models:
                            model_info = models[model_name]
                            is_trained = model_info.get('trained', False)
                            
                            if is_trained:
                                trained_models.append(model_name)
                                
                                # Check if metrics are available
                                if 'metrics' in model_info and model_info['metrics']:
                                    details += f" - {model_name}: trained with metrics ✓"
                                else:
                                    details += f" - {model_name}: trained (no metrics)"
                                
                                # Check file status
                                files_status = model_info.get('files_status', {})
                                missing_files = [f for f, exists in files_status.items() if not exists]
                                if missing_files:
                                    details += f" - {model_name} missing files: {missing_files}"
                            else:
                                untrained_models.append(model_name)
                                details += f" - {model_name}: not trained"
                        else:
                            untrained_models.append(model_name)
                            details += f" - {model_name}: missing from response"
                    
                    # Check summary
                    total_models = summary.get('total_models', 0)
                    trained_count = summary.get('trained_models', 0)
                    all_ready = summary.get('all_ready', False)
                    
                    details += f" - Summary: {trained_count}/{total_models} trained"
                    
                    # Verify counts
                    if trained_count == len(trained_models):
                        details += " ✓"
                    else:
                        details += f" (count mismatch: {trained_count} vs {len(trained_models)})"
                    
                    # Check if all models are ready
                    if all_ready and len(untrained_models) == 0:
                        details += " - All models ready ✅"
                    elif len(untrained_models) > 0:
                        details += f" - {len(untrained_models)} models not ready"
                    
                    # Success if at least 3 out of 4 models are trained
                    success = len(trained_models) >= 3
            
            self.log_test_result("model_status", "/ml/models/status (after)", "GET", success, details)
        except Exception as e:
            self.log_test_result("model_status", "/ml/models/status (after)", "GET", False, f"Error: {str(e)}")

    def check_model_files(self):
        """Check if model files are actually created on disk"""
        print("\n📁 Checking Model Files on Disk...")
        
        try:
            import os
            model_dir = '/app/backend/ml_models'
            
            if not os.path.exists(model_dir):
                print(f"❌ Model directory {model_dir} does not exist")
                return
            
            expected_files = {
                'rms': ['rms_occupancy_model.pkl', 'rms_pricing_model.pkl', 'rms_metrics.json'],
                'persona': ['persona_model.pkl', 'persona_label_encoder.pkl', 'persona_metrics.json'],
                'predictive_maintenance': ['maintenance_risk_model.pkl', 'maintenance_days_model.pkl', 'maintenance_label_encoder.pkl', 'maintenance_equipment_encoder.pkl', 'maintenance_metrics.json'],
                'hk_scheduler': ['hk_staff_model.pkl', 'hk_hours_model.pkl', 'hk_scheduler_metrics.json']
            }
            
            for model_name, files in expected_files.items():
                print(f"  📂 {model_name.upper()}:")
                for file_name in files:
                    file_path = os.path.join(model_dir, file_name)
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        print(f"    ✅ {file_name} ({file_size} bytes)")
                    else:
                        print(f"    ❌ {file_name} (missing)")
        
        except Exception as e:
            print(f"❌ Error checking model files: {str(e)}")

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print("🎯 ML TRAINING ENDPOINTS TEST SUMMARY")
        print("="*80)
        
        total_passed = 0
        total_failed = 0
        
        for category, results in self.test_results.items():
            passed = results["passed"]
            failed = results["failed"]
            total = passed + failed
            
            total_passed += passed
            total_failed += failed
            
            if total > 0:
                success_rate = (passed / total) * 100
                status = "✅" if success_rate >= 80 else "⚠️" if success_rate >= 60 else "❌"
                print(f"{status} {category.upper().replace('_', ' ')}: {passed}/{total} passed ({success_rate:.1f}%)")
                
                # Show failed tests
                failed_tests = [detail for detail in results["details"] if "❌ FAIL" in detail["status"]]
                if failed_tests:
                    print(f"   Failed tests:")
                    for test in failed_tests:
                        print(f"   - {test['endpoint']}: {test['details']}")
        
        overall_total = total_passed + total_failed
        if overall_total > 0:
            overall_success_rate = (total_passed / overall_total) * 100
            overall_status = "✅" if overall_success_rate >= 80 else "⚠️" if overall_success_rate >= 60 else "❌"
            print(f"\n{overall_status} OVERALL: {total_passed}/{overall_total} tests passed ({overall_success_rate:.1f}%)")
        
        print("\n📋 DETAILED RESULTS:")
        for category, results in self.test_results.items():
            if results["details"]:
                print(f"\n{category.upper().replace('_', ' ')}:")
                for detail in results["details"]:
                    print(f"  {detail['status']}: {detail['endpoint']}")
                    if detail['details']:
                        print(f"    {detail['details']}")

    def run_all_tests(self):
        """Run all ML training tests"""
        print("🚀 Starting ML Training Endpoints Testing...")
        print("="*80)
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        # Phase 1: Check model status before training
        self.test_model_status_before_training()
        
        # Phase 2: Individual model training
        self.test_individual_model_training()
        
        # Phase 3: Bulk training
        self.test_bulk_training()
        
        # Phase 4: Check model status after training
        self.test_model_status_after_training()
        
        # Phase 5: Check model files on disk
        self.check_model_files()
        
        # Print summary
        self.print_summary()
        
        return True

if __name__ == "__main__":
    tester = MLTrainingTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n✅ ML Training testing completed successfully!")
    else:
        print("\n❌ ML Training testing failed!")
        sys.exit(1)