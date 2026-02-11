#!/usr/bin/env python3
import requests
import json

BACKEND_URL = 'https://unitcare-1.preview.emergentagent.com/api'

# Login
response = requests.post(f'{BACKEND_URL}/auth/login', json={
    'email': 'test@hotel.com',
    'password': 'test123'
})

if response.status_code == 200:
    data = response.json()
    token = data['access_token']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    print('=== TESTING MARKETPLACE ENDPOINTS ===')
    
    # Test GET purchase orders first
    print('\n1. GET /marketplace/purchase-orders')
    response = requests.get(f'{BACKEND_URL}/marketplace/purchase-orders', headers=headers)
    print(f'Status: {response.status_code}')
    if response.status_code == 200:
        data = response.json()
        print(f'Response: {json.dumps(data, indent=2)[:500]}...')
    else:
        print(f'Error: {response.text}')
    
    # Test POST purchase order
    print('\n2. POST /marketplace/purchase-orders')
    po_data = {
        "supplier": "Test Supplier",
        "category": "cleaning",
        "items": [{"product_name": "Test cleaner", "quantity": 5, "unit_price": 10.0}],
        "total_amount": 50.0,
        "delivery_location": "Test Location",
        "status": "approved"
    }
    response = requests.post(f'{BACKEND_URL}/marketplace/purchase-orders', json=po_data, headers=headers)
    print(f'Status: {response.status_code}')
    if response.status_code in [200, 201]:
        data = response.json()
        print(f'Created PO: {json.dumps(data, indent=2)[:500]}...')
        po_id = data.get('id')
        
        # Test GET again to see if it shows up
        print('\n3. GET /marketplace/purchase-orders (after creation)')
        response = requests.get(f'{BACKEND_URL}/marketplace/purchase-orders', headers=headers)
        print(f'Status: {response.status_code}')
        if response.status_code == 200:
            data = response.json()
            purchase_orders = data.get('purchase_orders', [])
            print(f'Total POs now: {len(purchase_orders)}')
            if purchase_orders:
                print(f'First PO: {purchase_orders[0]}')
        else:
            print(f'Error: {response.text}')
    else:
        print(f'Error: {response.text}')
        
else:
    print(f'Login failed: {response.status_code} - {response.text}')