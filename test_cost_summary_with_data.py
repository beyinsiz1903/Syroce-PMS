#!/usr/bin/env python3
import requests
import json
from datetime import datetime, timezone

BACKEND_URL = 'https://app-audit-9.preview.emergentagent.com/api'

# Login
response = requests.post(f'{BACKEND_URL}/auth/login', json={
    'email': 'test@hotel.com',
    'password': 'test123'
})

if response.status_code == 200:
    data = response.json()
    token = data['access_token']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    print('=== CREATING PURCHASE ORDERS WITH APPROVED STATUS ===')
    
    # Create purchase orders with approved status
    test_pos = [
        {
            "supplier": "CleanCorp",
            "category": "cleaning",
            "items": [{"product_name": "All-purpose cleaner", "quantity": 10, "unit_price": 15.0}],
            "total_amount": 150.0,
            "delivery_location": "Housekeeping Storage",
            "status": "approved"
        },
        {
            "supplier": "FoodSupply Inc", 
            "category": "food",
            "items": [{"product_name": "Fresh vegetables", "quantity": 50, "unit_price": 8.0}],
            "total_amount": 400.0,
            "delivery_location": "Kitchen",
            "status": "received"
        },
        {
            "supplier": "TechFix Ltd",
            "category": "maintenance", 
            "items": [{"product_name": "HVAC filters", "quantity": 5, "unit_price": 25.0}],
            "total_amount": 125.0,
            "delivery_location": "Maintenance Room",
            "status": "completed"
        }
    ]
    
    created_pos = []
    for po_data in test_pos:
        response = requests.post(f'{BACKEND_URL}/marketplace/purchase-orders', json=po_data, headers=headers)
        if response.status_code in [200, 201]:
            po = response.json()
            created_pos.append(po)
            print(f'✅ Created PO: {po_data["supplier"]} - ${po_data["total_amount"]} - Status: {po.get("status")}')
            
            # Update status to approved/received/completed if it was set to pending
            if po.get('status') == 'pending' and po_data['status'] != 'pending':
                po_id = po.get('id')
                if po_data['status'] == 'approved':
                    approve_response = requests.post(f'{BACKEND_URL}/marketplace/purchase-orders/{po_id}/approve', 
                                                   json={"approval_notes": "Test approval"}, headers=headers)
                    if approve_response.status_code in [200, 201]:
                        print(f'  ✅ Approved PO {po_id}')
                    else:
                        print(f'  ⚠️ Failed to approve PO {po_id}: {approve_response.status_code}')
        else:
            print(f'❌ Failed to create PO for {po_data["supplier"]}: {response.status_code} - {response.text}')
    
    print(f'\\n=== TESTING COST SUMMARY WITH DATA ===')
    
    # Test cost summary
    response = requests.get(f'{BACKEND_URL}/reports/cost-summary', headers=headers)
    if response.status_code == 200:
        cost_data = response.json()
        print('Cost Summary Response:')
        print(json.dumps(cost_data, indent=2))
        
        # Verify the data
        total_costs = cost_data.get('total_mtd_costs', 0)
        print(f'\\nTotal MTD Costs: ${total_costs}')
        
        if total_costs > 0:
            print('✅ Cost summary is working with purchase order data!')
            
            # Check category breakdown
            categories = cost_data.get('cost_categories', {})
            print('\\nCategory Breakdown:')
            for cat, amount in categories.items():
                if amount > 0:
                    print(f'  {cat}: ${amount}')
        else:
            print('⚠️ Cost summary still shows $0 - investigating...')
            
            # Check what purchase orders exist in the database
            print('\\nChecking purchase orders in database...')
            response = requests.get(f'{BACKEND_URL}/marketplace/purchase-orders', headers=headers)
            if response.status_code == 200:
                po_data = response.json()
                orders = po_data.get('orders', [])
                print(f'Total orders in DB: {len(orders)}')
                
                # Check status and dates
                today = datetime.now(timezone.utc)
                month_start = today.replace(day=1)
                
                for order in orders:
                    created_at = order.get('created_at', '')
                    status = order.get('status', '')
                    amount = order.get('total_amount', 0)
                    category = order.get('category', '')
                    
                    print(f'  Order: ${amount}, Status: {status}, Category: {category}, Created: {created_at}')
                    
                    # Check if it should be included
                    try:
                        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        is_this_month = created_date >= month_start
                        is_approved_status = status in ['approved', 'received', 'completed']
                        
                        print(f'    This month: {is_this_month}, Approved status: {is_approved_status}')
                    except:
                        print(f'    Could not parse date: {created_at}')
    else:
        print(f'Cost summary failed: {response.status_code} - {response.text}')
        
else:
    print(f'Login failed: {response.status_code} - {response.text}')