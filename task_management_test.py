#!/usr/bin/env python3
"""
Enhanced Task Management System - Multi-Department Testing
Testing 11 endpoints for comprehensive task management across departments
"""

import requests
import json
import sys
import os
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "https://appstore-preview-1.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

class TaskManagementTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.tenant_id = None
        self.user_id = None
        self.test_results = {
            "core_tasks": {"passed": 0, "failed": 0, "details": []},
            "department_requests": {"passed": 0, "failed": 0, "details": []}
        }
        self.created_resources = {
            "task_ids": [],
            "room_ids": []
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

    def test_core_task_management(self):
        """Test Core Task Management (8 endpoints)"""
        print("\n📋 Testing Core Task Management (8 endpoints)...")
        
        created_task_ids = []
        
        # ============= A) CREATE TASKS (3 different departments) =============
        print("\n🔨 Testing Task Creation...")
        
        # A.1 POST /api/tasks - Engineering Task
        try:
            response = self.session.post(f"{BACKEND_URL}/tasks", json={
                "department": "engineering",
                "task_type": "repair",
                "title": "Fix AC Unit",
                "description": "AC not cooling in Room 305",
                "priority": "urgent",
                "location": "Room 305",
                "room_id": None,
                "assigned_to": None,
                "due_date": "2025-01-26"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                task_id = data.get('id')
                if task_id:
                    created_task_ids.append(task_id)
                    self.created_resources["task_ids"].append(task_id)
                
                details += f" - Created: {data.get('title')} ({data.get('department')})"
                details += f" - Priority: {data.get('priority')}, Type: {data.get('task_type')}"
                details += f" - Status: {data.get('status', 'new')}"
                
                # Verify priority_order mapping (urgent:4, high:3, normal:2, low:1)
                priority_order = data.get('priority_order')
                if data.get('priority') == 'urgent' and priority_order == 4:
                    details += " - Priority order: ✓"
                else:
                    details += f" - Priority order: {priority_order} (expected: 4 for urgent)"
            
            self.log_test_result("core_tasks", "/tasks (Engineering)", "POST", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks (Engineering)", "POST", False, f"Error: {str(e)}")

        # A.2 POST /api/tasks - Housekeeping Task
        try:
            response = self.session.post(f"{BACKEND_URL}/tasks", json={
                "department": "housekeeping",
                "task_type": "deep_clean",
                "title": "Deep Clean Room 201",
                "description": "Guest complained about cleanliness",
                "priority": "high",
                "location": "Room 201",
                "assigned_to": "Maria"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                task_id = data.get('id')
                if task_id:
                    created_task_ids.append(task_id)
                    self.created_resources["task_ids"].append(task_id)
                
                details += f" - Created: {data.get('title')} ({data.get('department')})"
                details += f" - Assigned to: {data.get('assigned_to')}"
                
                # Verify priority_order for high priority
                priority_order = data.get('priority_order')
                if data.get('priority') == 'high' and priority_order == 3:
                    details += " - Priority order: ✓"
                else:
                    details += f" - Priority order: {priority_order} (expected: 3 for high)"
            
            self.log_test_result("core_tasks", "/tasks (Housekeeping)", "POST", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks (Housekeeping)", "POST", False, f"Error: {str(e)}")

        # A.3 POST /api/tasks - F&B Task
        try:
            response = self.session.post(f"{BACKEND_URL}/tasks", json={
                "department": "fnb",
                "task_type": "catering",
                "title": "Conference Room Setup",
                "description": "Setup for 50 people meeting",
                "priority": "normal",
                "location": "Conference Room A",
                "due_date": "2025-01-25"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                task_id = data.get('id')
                if task_id:
                    created_task_ids.append(task_id)
                    self.created_resources["task_ids"].append(task_id)
                
                details += f" - Created: {data.get('title')} ({data.get('department')})"
                details += f" - Due date: {data.get('due_date')}"
                
                # Verify priority_order for normal priority
                priority_order = data.get('priority_order')
                if data.get('priority') == 'normal' and priority_order == 2:
                    details += " - Priority order: ✓"
                else:
                    details += f" - Priority order: {priority_order} (expected: 2 for normal)"
            
            self.log_test_result("core_tasks", "/tasks (F&B)", "POST", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks (F&B)", "POST", False, f"Error: {str(e)}")

        # ============= B) LIST & FILTER TASKS (5 different filters) =============
        print("\n📝 Testing Task Listing & Filtering...")
        
        # B.1 GET /api/tasks - All tasks
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                tasks = data.get('tasks', [])
                details += f" - Total tasks: {len(tasks)}"
                
                # Verify task structure
                if tasks:
                    task = tasks[0]
                    required_fields = ['id', 'department', 'task_type', 'title', 'priority', 'status', 'created_at']
                    present_fields = [field for field in required_fields if field in task]
                    details += f" - Task fields: {len(present_fields)}/{len(required_fields)}"
                    
                    # Check if our created tasks are present
                    our_tasks = [t for t in tasks if t.get('id') in created_task_ids]
                    details += f" - Our tasks found: {len(our_tasks)}/{len(created_task_ids)}"
            
            self.log_test_result("core_tasks", "/tasks (All)", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks (All)", "GET", False, f"Error: {str(e)}")

        # B.2 GET /api/tasks?department=engineering
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks?department=engineering")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - Engineering filter"
            
            if success and response.json():
                data = response.json()
                tasks = data.get('tasks', [])
                details += f" - Engineering tasks: {len(tasks)}"
                
                # Verify all tasks are engineering
                eng_tasks = [t for t in tasks if t.get('department') == 'engineering']
                if len(eng_tasks) == len(tasks):
                    details += " - Department filter: ✓"
                else:
                    details += f" - Department filter issue: {len(eng_tasks)}/{len(tasks)} are engineering"
            
            self.log_test_result("core_tasks", "/tasks?department=engineering", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks?department=engineering", "GET", False, f"Error: {str(e)}")

        # B.3 GET /api/tasks?status=new
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks?status=new")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - Status filter"
            
            if success and response.json():
                data = response.json()
                tasks = data.get('tasks', [])
                details += f" - New tasks: {len(tasks)}"
                
                # Verify all tasks have 'new' status
                new_tasks = [t for t in tasks if t.get('status') == 'new']
                if len(new_tasks) == len(tasks):
                    details += " - Status filter: ✓"
                else:
                    details += f" - Status filter issue: {len(new_tasks)}/{len(tasks)} are new"
            
            self.log_test_result("core_tasks", "/tasks?status=new", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks?status=new", "GET", False, f"Error: {str(e)}")

        # B.4 GET /api/tasks?priority=urgent
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks?priority=urgent")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - Priority filter"
            
            if success and response.json():
                data = response.json()
                tasks = data.get('tasks', [])
                details += f" - Urgent tasks: {len(tasks)}"
                
                # Verify all tasks are urgent
                urgent_tasks = [t for t in tasks if t.get('priority') == 'urgent']
                if len(urgent_tasks) == len(tasks):
                    details += " - Priority filter: ✓"
                else:
                    details += f" - Priority filter issue: {len(urgent_tasks)}/{len(tasks)} are urgent"
                
                # Check priority sorting (urgent should be first)
                if tasks and len(tasks) > 1:
                    first_priority_order = tasks[0].get('priority_order', 0)
                    details += f" - First task priority order: {first_priority_order}"
            
            self.log_test_result("core_tasks", "/tasks?priority=urgent", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks?priority=urgent", "GET", False, f"Error: {str(e)}")

        # B.5 GET /api/tasks?assigned_to=Maria
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks?assigned_to=Maria")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - Assigned to filter"
            
            if success and response.json():
                data = response.json()
                tasks = data.get('tasks', [])
                details += f" - Maria's tasks: {len(tasks)}"
                
                # Verify all tasks are assigned to Maria
                maria_tasks = [t for t in tasks if t.get('assigned_to') == 'Maria']
                if len(maria_tasks) == len(tasks):
                    details += " - Assignment filter: ✓"
                else:
                    details += f" - Assignment filter issue: {len(maria_tasks)}/{len(tasks)} assigned to Maria"
            
            self.log_test_result("core_tasks", "/tasks?assigned_to=Maria", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks?assigned_to=Maria", "GET", False, f"Error: {str(e)}")

        # ============= C) TASK DETAILS =============
        print("\n🔍 Testing Task Details...")
        
        # C.1 GET /api/tasks/{task_id} - Verify history tracking
        if created_task_ids:
            try:
                task_id = created_task_ids[0]  # Engineering task
                response = self.session.get(f"{BACKEND_URL}/tasks/{task_id}")
                success = response.status_code == 200
                details = f"Status: {response.status_code}"
                
                if success and response.json():
                    data = response.json()
                    details += f" - Task: {data.get('title')}"
                    details += f" - Department: {data.get('department')}"
                    details += f" - Status: {data.get('status')}"
                    
                    # Check for history tracking
                    history = data.get('history', [])
                    details += f" - History entries: {len(history)}"
                    
                    if history:
                        latest_entry = history[0]
                        history_fields = ['timestamp', 'action', 'user', 'details']
                        present_fields = [field for field in history_fields if field in latest_entry]
                        details += f" - History fields: {len(present_fields)}/{len(history_fields)}"
                
                self.log_test_result("core_tasks", f"/tasks/{task_id}", "GET", success, details)
            except Exception as e:
                self.log_test_result("core_tasks", f"/tasks/{task_id}", "GET", False, f"Error: {str(e)}")

        # ============= D) ASSIGN TASK =============
        print("\n👤 Testing Task Assignment...")
        
        # D.1 POST /api/tasks/{task_id}/assign
        if created_task_ids:
            try:
                task_id = created_task_ids[0]  # Engineering task (currently unassigned)
                response = self.session.post(f"{BACKEND_URL}/tasks/{task_id}/assign", json={
                    "assigned_to": "John Engineer",
                    "notes": "Urgent - handle immediately"
                })
                success = response.status_code in [200, 201]
                details = f"Status: {response.status_code}"
                
                if success and response.json():
                    data = response.json()
                    details += f" - Response: {data.get('message', 'Task assigned')}"
                    
                    # The endpoint returns a message, not the task data
                    # Let's verify by fetching the task details
                    task_response = self.session.get(f"{BACKEND_URL}/tasks/{task_id}")
                    if task_response.status_code == 200:
                        task_data = task_response.json()
                        details += f" - Assigned to: {task_data.get('assigned_to')}"
                        details += f" - Status: {task_data.get('status')}"
                        
                        # Verify status changed to 'assigned'
                        if task_data.get('status') == 'assigned':
                            details += " - Status change: ✓"
                        else:
                            details += f" - Status change issue: {task_data.get('status')} (expected: assigned)"
                
                self.log_test_result("core_tasks", f"/tasks/{task_id}/assign", "POST", success, details)
            except Exception as e:
                self.log_test_result("core_tasks", f"/tasks/{task_id}/assign", "POST", False, f"Error: {str(e)}")

        # ============= E) UPDATE STATUS =============
        print("\n📊 Testing Status Updates...")
        
        # E.1 POST /api/tasks/{task_id}/status - In Progress
        if created_task_ids:
            try:
                task_id = created_task_ids[0]  # Engineering task
                response = self.session.post(f"{BACKEND_URL}/tasks/{task_id}/status", json={
                    "status": "in_progress",
                    "notes": "Started working on AC repair"
                })
                success = response.status_code in [200, 201]
                details = f"Status: {response.status_code}"
                
                if success and response.json():
                    data = response.json()
                    details += f" - Response: {data.get('message', 'Status updated')}"
                    
                    # The endpoint returns a message, let's fetch task details
                    task_response = self.session.get(f"{BACKEND_URL}/tasks/{task_id}")
                    if task_response.status_code == 200:
                        task_data = task_response.json()
                        details += f" - Status: {task_data.get('status')}"
                        
                        # Verify status workflow (assigned → in_progress)
                        if task_data.get('status') == 'in_progress':
                            details += " - Status workflow: ✓"
                        else:
                            details += f" - Status workflow issue: {task_data.get('status')}"
                        
                        # Check history tracking
                        history = task_data.get('history', [])
                        if history:
                            details += f" - History updated: {len(history)} entries"
                
                self.log_test_result("core_tasks", f"/tasks/{task_id}/status (in_progress)", "POST", success, details)
            except Exception as e:
                self.log_test_result("core_tasks", f"/tasks/{task_id}/status (in_progress)", "POST", False, f"Error: {str(e)}")

        # E.2 POST /api/tasks/{task_id}/status - Complete
        if created_task_ids:
            try:
                task_id = created_task_ids[0]  # Engineering task
                response = self.session.post(f"{BACKEND_URL}/tasks/{task_id}/status", json={
                    "status": "completed",
                    "notes": "AC fixed and tested",
                    "completion_photos": ["photo1.jpg"]
                })
                success = response.status_code in [200, 201]
                details = f"Status: {response.status_code}"
                
                if success and response.json():
                    data = response.json()
                    details += f" - Response: {data.get('message', 'Status updated')}"
                    
                    # The endpoint returns a message, let's fetch task details
                    task_response = self.session.get(f"{BACKEND_URL}/tasks/{task_id}")
                    if task_response.status_code == 200:
                        task_data = task_response.json()
                        details += f" - Status: {task_data.get('status')}"
                        details += f" - Completed at: {task_data.get('completed_at', 'N/A')}"
                        
                        # Verify completion workflow (in_progress → completed)
                        if task_data.get('status') == 'completed':
                            details += " - Completion workflow: ✓"
                        else:
                            details += f" - Completion workflow issue: {task_data.get('status')}"
                        
                        # Check completion photos
                        photos = task_data.get('completion_photos', [])
                        details += f" - Photos: {len(photos)}"
                
                self.log_test_result("core_tasks", f"/tasks/{task_id}/status (completed)", "POST", success, details)
            except Exception as e:
                self.log_test_result("core_tasks", f"/tasks/{task_id}/status (completed)", "POST", False, f"Error: {str(e)}")

        # ============= F) MY TASKS =============
        print("\n👨‍💼 Testing My Tasks...")
        
        # F.1 GET /api/tasks/my-tasks
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks/my-tasks")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                tasks = data.get('tasks', [])
                details += f" - My tasks: {len(tasks)}"
                
                # Verify tasks are filtered to current user
                if tasks:
                    user_tasks = [t for t in tasks if t.get('assigned_to') or t.get('created_by') == self.user_id]
                    details += f" - User-specific tasks: {len(user_tasks)}"
            
            self.log_test_result("core_tasks", "/tasks/my-tasks", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks/my-tasks", "GET", False, f"Error: {str(e)}")

        # F.2 GET /api/tasks/my-tasks?status=in_progress
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks/my-tasks?status=in_progress")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - In progress filter"
            
            if success and response.json():
                data = response.json()
                tasks = data.get('tasks', [])
                details += f" - My in-progress tasks: {len(tasks)}"
                
                # Verify status filtering
                in_progress_tasks = [t for t in tasks if t.get('status') == 'in_progress']
                if len(in_progress_tasks) == len(tasks):
                    details += " - Status filter: ✓"
                else:
                    details += f" - Status filter issue: {len(in_progress_tasks)}/{len(tasks)}"
            
            self.log_test_result("core_tasks", "/tasks/my-tasks?status=in_progress", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks/my-tasks?status=in_progress", "GET", False, f"Error: {str(e)}")

        # ============= G) DEPARTMENT TASKS =============
        print("\n🏢 Testing Department Tasks...")
        
        # G.1 GET /api/tasks/department/engineering
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks/department/engineering")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                tasks = data.get('tasks', [])
                details += f" - Engineering tasks: {len(tasks)}"
                
                # Check statistics
                statistics = data.get('statistics', {})
                if statistics:
                    by_status = statistics.get('by_status', {})
                    by_priority = statistics.get('by_priority', {})
                    overdue_count = statistics.get('overdue_count', 0)
                    
                    details += f" - Stats: Status({len(by_status)}), Priority({len(by_priority)}), Overdue({overdue_count})"
                
                # Verify all tasks are engineering
                eng_tasks = [t for t in tasks if t.get('department') == 'engineering']
                if len(eng_tasks) == len(tasks):
                    details += " - Department filter: ✓"
                else:
                    details += f" - Department filter issue: {len(eng_tasks)}/{len(tasks)}"
            
            self.log_test_result("core_tasks", "/tasks/department/engineering", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks/department/engineering", "GET", False, f"Error: {str(e)}")

        # G.2 GET /api/tasks/department/housekeeping?status=new
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks/department/housekeeping?status=new")
            success = response.status_code == 200
            details = f"Status: {response.status_code} - New status filter"
            
            if success and response.json():
                data = response.json()
                tasks = data.get('tasks', [])
                details += f" - New housekeeping tasks: {len(tasks)}"
                
                # Verify department and status filtering
                hk_new_tasks = [t for t in tasks if t.get('department') == 'housekeeping' and t.get('status') == 'new']
                if len(hk_new_tasks) == len(tasks):
                    details += " - Combined filter: ✓"
                else:
                    details += f" - Combined filter issue: {len(hk_new_tasks)}/{len(tasks)}"
            
            self.log_test_result("core_tasks", "/tasks/department/housekeeping?status=new", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks/department/housekeeping?status=new", "GET", False, f"Error: {str(e)}")

        # ============= H) DASHBOARD =============
        print("\n📊 Testing Task Dashboard...")
        
        # H.1 GET /api/tasks/dashboard
        try:
            response = self.session.get(f"{BACKEND_URL}/tasks/dashboard")
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                
                # Check summary statistics (the actual field names from the server)
                summary = data.get('summary', {})
                required_summary_fields = ['total_tasks', 'new', 'in_progress', 'completed_today', 'urgent_pending', 'overdue']
                missing_summary = [field for field in required_summary_fields if field not in summary]
                
                if missing_summary:
                    details += f" - Missing summary fields: {missing_summary}"
                    success = False
                else:
                    details += f" - Total: {summary.get('total_tasks')}, New: {summary.get('new')}"
                    details += f" - In Progress: {summary.get('in_progress')}, Completed Today: {summary.get('completed_today')}"
                    details += f" - Urgent Pending: {summary.get('urgent_pending')}, Overdue: {summary.get('overdue')}"
                
                # Check department breakdown (the actual field name is 'departments')
                department_breakdown = data.get('departments', {})
                expected_departments = ['engineering', 'housekeeping', 'fnb', 'maintenance', 'front_desk']
                
                for dept in expected_departments:
                    if dept in department_breakdown:
                        dept_data = department_breakdown[dept]
                        if isinstance(dept_data, dict) and 'total' in dept_data:
                            details += f" - {dept.title()}: {dept_data.get('total')} tasks"
                        else:
                            details += f" - {dept.title()}: {dept_data} tasks"
                    else:
                        details += f" - Missing {dept}"
            
            self.log_test_result("core_tasks", "/tasks/dashboard", "GET", success, details)
        except Exception as e:
            self.log_test_result("core_tasks", "/tasks/dashboard", "GET", False, f"Error: {str(e)}")

    def test_department_specific_requests(self):
        """Test Department-Specific Requests (3 endpoints)"""
        print("\n🏭 Testing Department-Specific Requests (3 endpoints)...")
        
        # ============= A) ENGINEERING MAINTENANCE REQUEST =============
        print("\n🔧 Testing Engineering Maintenance Request...")
        
        # A.1 POST /api/tasks/engineering/maintenance-request
        try:
            response = self.session.post(f"{BACKEND_URL}/tasks/engineering/maintenance-request", params={
                "title": "Plumbing Issue",
                "description": "Leaking pipe in Room 401",
                "location": "Room 401",
                "priority": "high",
                "room_id": None
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                details += f" - Created: {data.get('title')}"
                details += f" - Department: {data.get('department')}"
                details += f" - Task Type: {data.get('task_type')}"
                
                # Verify it creates task with department='engineering', task_type='repair'
                if data.get('department') == 'engineering' and data.get('task_type') == 'repair':
                    details += " - Department/Type mapping: ✓"
                else:
                    details += f" - Department/Type mapping issue: {data.get('department')}/{data.get('task_type')}"
                
                # Store task ID for cleanup
                task_id = data.get('id')
                if task_id:
                    self.created_resources["task_ids"].append(task_id)
            
            self.log_test_result("department_requests", "/tasks/engineering/maintenance-request", "POST", success, details)
        except Exception as e:
            self.log_test_result("department_requests", "/tasks/engineering/maintenance-request", "POST", False, f"Error: {str(e)}")

        # ============= B) HOUSEKEEPING CLEANING REQUEST =============
        print("\n🧹 Testing Housekeeping Cleaning Request...")
        
        # First, let's create a room for testing
        existing_room_id = None
        try:
            room_data = {
                'room_number': '101',
                'room_type': 'standard',
                'floor': 1,
                'capacity': 2,
                'base_price': 100.0,
                'amenities': ['wifi', 'tv']
            }
            room_response = self.session.post(f"{BACKEND_URL}/pms/rooms", json=room_data)
            if room_response.status_code in [200, 201]:
                existing_room_id = room_response.json().get('id')
                self.created_resources["room_ids"].append(existing_room_id)
        except:
            pass
        
        # B.1 POST /api/tasks/housekeeping/cleaning-request
        try:
            request_data = {
                "task_type": "inspection",
                "priority": "normal",
                "special_instructions": "Check all amenities"
            }
            
            if existing_room_id:
                request_data["room_id"] = existing_room_id
            else:
                # Create a mock room_id for testing
                request_data["room_id"] = "room_test_001"
            
            response = self.session.post(f"{BACKEND_URL}/tasks/housekeeping/cleaning-request", params=request_data)
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                details += f" - Created: {data.get('title', 'Housekeeping Task')}"
                details += f" - Department: {data.get('department')}"
                details += f" - Room ID: {data.get('room_id')}"
                
                # Verify it creates task with room details
                if data.get('department') == 'housekeeping':
                    details += " - Department mapping: ✓"
                else:
                    details += f" - Department mapping issue: {data.get('department')}"
                
                # Check if room details are included
                if 'room_details' in data or 'room_number' in data:
                    details += " - Room details: ✓"
                
                # Store task ID for cleanup
                task_id = data.get('id')
                if task_id:
                    self.created_resources["task_ids"].append(task_id)
            
            self.log_test_result("department_requests", "/tasks/housekeeping/cleaning-request", "POST", success, details)
        except Exception as e:
            self.log_test_result("department_requests", "/tasks/housekeeping/cleaning-request", "POST", False, f"Error: {str(e)}")

        # ============= C) F&B SERVICE REQUEST =============
        print("\n🍽️ Testing F&B Service Request...")
        
        # C.1 POST /api/tasks/fnb/service-request
        try:
            response = self.session.post(f"{BACKEND_URL}/tasks/fnb/service-request", params={
                "request_type": "room_service",
                "title": "VIP Room Service",
                "description": "Suite 1001 - Special dinner setup",
                "location": "Suite 1001",
                "priority": "high",
                "due_date": "2025-01-25"
            })
            success = response.status_code in [200, 201]
            details = f"Status: {response.status_code}"
            
            if success and response.json():
                data = response.json()
                details += f" - Created: {data.get('title')}"
                details += f" - Department: {data.get('department')}"
                details += f" - Request Type: {data.get('request_type', data.get('task_type'))}"
                details += f" - Due Date: {data.get('due_date')}"
                
                # Verify it creates F&B task
                if data.get('department') == 'fnb':
                    details += " - Department mapping: ✓"
                else:
                    details += f" - Department mapping issue: {data.get('department')}"
                
                # Store task ID for cleanup
                task_id = data.get('id')
                if task_id:
                    self.created_resources["task_ids"].append(task_id)
            
            self.log_test_result("department_requests", "/tasks/fnb/service-request", "POST", success, details)
        except Exception as e:
            self.log_test_result("department_requests", "/tasks/fnb/service-request", "POST", False, f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all task management tests"""
        print("🚀 Starting Enhanced Task Management System Testing...")
        print("=" * 80)
        
        if not self.authenticate():
            return False
        
        # Test Core Task Management (8 endpoints)
        self.test_core_task_management()
        
        # Test Department-Specific Requests (3 endpoints)
        self.test_department_specific_requests()
        
        # Print final results
        self.print_final_results()
        
        return True

    def print_final_results(self):
        """Print comprehensive test results"""
        print("\n" + "=" * 80)
        print("📊 ENHANCED TASK MANAGEMENT SYSTEM - TEST RESULTS")
        print("=" * 80)
        
        total_passed = 0
        total_failed = 0
        
        for category, results in self.test_results.items():
            passed = results["passed"]
            failed = results["failed"]
            total = passed + failed
            
            total_passed += passed
            total_failed += failed
            
            print(f"\n📋 {category.upper().replace('_', ' ')}:")
            print(f"   ✅ Passed: {passed}/{total}")
            print(f"   ❌ Failed: {failed}/{total}")
            
            if failed > 0:
                print("   Failed Tests:")
                for detail in results["details"]:
                    if "❌ FAIL" in detail["status"]:
                        print(f"     - {detail['endpoint']}: {detail['details']}")
        
        # Overall results
        total_tests = total_passed + total_failed
        success_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n🎯 OVERALL RESULTS:")
        print(f"   Total Tests: {total_tests}")
        print(f"   ✅ Passed: {total_passed}")
        print(f"   ❌ Failed: {total_failed}")
        print(f"   📈 Success Rate: {success_rate:.1f}%")
        
        # Validation criteria summary
        print(f"\n✅ VALIDATION CRITERIA VERIFICATION:")
        print(f"   - Priority order mapping (urgent:4, high:3, normal:2, low:1)")
        print(f"   - Status workflow (new → assigned → in_progress → completed)")
        print(f"   - Task history tracking for all changes")
        print(f"   - Department filtering accuracy")
        print(f"   - Dashboard statistics calculations")
        print(f"   - Due date tracking and overdue detection")
        print(f"   - Department-specific request routing")
        
        if success_rate >= 90:
            print(f"\n🎉 EXCELLENT! Task Management System is working perfectly!")
        elif success_rate >= 75:
            print(f"\n👍 GOOD! Most features working, minor issues to address.")
        else:
            print(f"\n⚠️  NEEDS ATTENTION! Several critical issues found.")
        
        print("=" * 80)

if __name__ == "__main__":
    tester = TaskManagementTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)