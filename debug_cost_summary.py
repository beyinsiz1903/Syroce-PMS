#!/usr/bin/env python3
import requests
import json
from datetime import datetime

BACKEND_URL = 'https://pms-i18next-demo.preview.emergentagent.com/api'

# Login
response = requests.post(f'{BACKEND_URL}/auth/login', json={
    'email': 'test@hotel.com',
    'password': 'test123'
})

if response.status_code == 200:
    data = response.json()
    token = data['access_token']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    print('=== COST SUMMARY RESPONSE ===')
    response = requests.get(f'{BACKEND_URL}/reports/cost-summary', headers=headers)
    if response.status_code == 200:
        cost_data = response.json()
        print(json.dumps(cost_data, indent=2))
    else:
        print(f'Cost summary failed: {response.status_code} - {response.text}')
    
    print('\n=== PURCHASE ORDERS ===')
    response = requests.get(f'{BACKEND_URL}/marketplace/purchase-orders', headers=headers)
    if response.status_code == 200:
        po_data = response.json()
        purchase_orders = po_data.get('purchase_orders', [])
        print(f'Total POs: {len(purchase_orders)}')
        for po in purchase_orders[:5]:  # Show first 5
            print(f'PO ID: {po.get("id")}, Status: {po.get("status")}, Amount: ${po.get("total_amount")}, Category: {po.get("category")}, Created: {po.get("created_at")}')
    else:
        print(f'PO list failed: {response.status_code} - {response.text}')
else:
    print(f'Login failed: {response.status_code} - {response.text}')