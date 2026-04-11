#!/usr/bin/env python3
"""
Demo Data Generator for Finance Mobile Features
Creates sample data for testing Turkish finance management features
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import uuid

# MongoDB connection
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "hotel_pms"

async def create_demo_data():
    """Create demo data for finance mobile features"""
    
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    print("🏦 Creating Finance Mobile Demo Data...")
    
    # Get first tenant
    tenant = await db.tenants.find_one()
    if not tenant:
        print("❌ No tenant found. Please register a tenant first.")
        return
    
    tenant_id = tenant['id']
    print(f"✅ Using tenant: {tenant.get('hotel_name', 'Unknown')}")
    
    # 1. Create Bank Accounts
    print("\n💳 Creating Bank Accounts...")
    
    banks = [
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'bank_name': 'Garanti BBVA',
            'account_number': '1234567890',
            'iban': 'TR330006100519786457841326',
            'currency': 'TRY',
            'current_balance': 250000.00,
            'available_balance': 245000.00,
            'account_type': 'checking',
            'is_active': True,
            'api_enabled': False,
            'api_credentials': None,
            'last_sync': datetime.now(timezone.utc),
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'bank_name': 'İş Bankası',
            'account_number': '9876543210',
            'iban': 'TR640006400000111222333444',
            'currency': 'TRY',
            'current_balance': 180000.00,
            'available_balance': 175000.00,
            'account_type': 'checking',
            'is_active': True,
            'api_enabled': False,
            'api_credentials': None,
            'last_sync': datetime.now(timezone.utc),
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        },
        {
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'bank_name': 'Yapı Kredi',
            'account_number': '5555666677',
            'iban': 'TR880006700000000012345678',
            'currency': 'USD',
            'current_balance': 15000.00,
            'available_balance': 14500.00,
            'account_type': 'savings',
            'is_active': True,
            'api_enabled': False,
            'api_credentials': None,
            'last_sync': datetime.now(timezone.utc),
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
    ]
    
    # Delete existing bank accounts for this tenant
    await db.bank_accounts.delete_many({'tenant_id': tenant_id})
    
    # Insert bank accounts
    result = await db.bank_accounts.insert_many(banks)
    print(f"✅ Created {len(result.inserted_ids)} bank accounts")
    
    # 2. Create Companies with Credit Limits
    print("\n🏢 Creating Companies with Credit Limits...")
    
    companies = await db.companies.find({'tenant_id': tenant_id}).limit(5).to_list(5)
    
    if not companies:
        print("⚠️  No companies found. Creating sample companies...")
        
        sample_companies = [
            {
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'name': 'Acme Travel Agency',
                'corporate_code': 'ACME001',
                'tax_number': '1234567890',
                'billing_address': 'İstiklal Cad. No:123 Beyoğlu, İstanbul',
                'contact_person': 'Ahmet Yılmaz',
                'contact_email': 'ahmet@acmetravel.com',
                'contact_phone': '+90 212 555 1234',
                'contracted_rate': 800.00,
                'default_rate_type': 'corporate',
                'default_market_segment': 'corporate',
                'default_cancellation_policy': 'flexible',
                'payment_terms': 'Net 30',
                'status': 'active',
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'name': 'Global Tourism Ltd',
                'corporate_code': 'GLOBAL001',
                'tax_number': '9876543210',
                'billing_address': 'Bağdat Cad. No:456 Kadıköy, İstanbul',
                'contact_person': 'Ayşe Demir',
                'contact_email': 'ayse@globaltourism.com',
                'contact_phone': '+90 216 555 5678',
                'contracted_rate': 950.00,
                'default_rate_type': 'corporate',
                'default_market_segment': 'corporate',
                'default_cancellation_policy': 'moderate',
                'payment_terms': 'Net 60',
                'status': 'active',
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': tenant_id,
                'name': 'Business Express Group',
                'corporate_code': 'BEG001',
                'tax_number': '5555666677',
                'billing_address': 'Büyükdere Cad. No:789 Şişli, İstanbul',
                'contact_person': 'Mehmet Kaya',
                'contact_email': 'mehmet@businessexpress.com',
                'contact_phone': '+90 212 555 9999',
                'contracted_rate': 700.00,
                'default_rate_type': 'corporate',
                'default_market_segment': 'corporate',
                'default_cancellation_policy': 'strict',
                'payment_terms': 'Net 45',
                'status': 'active',
                'created_at': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }
        ]
        
        result = await db.companies.insert_many(sample_companies)
        companies = sample_companies
        print(f"✅ Created {len(result.inserted_ids)} companies")
    
    # Create Credit Limits for companies
    credit_limits = []
    
    for i, company in enumerate(companies[:3]):
        # Vary the credit scenarios
        if i == 0:
            # Company exceeding limit
            credit_limit = 50000.00
            current_debt = 55000.00
        elif i == 1:
            # Company near limit (95%)
            credit_limit = 100000.00
            current_debt = 95000.00
        else:
            # Company within limit
            credit_limit = 75000.00
            current_debt = 45000.00
        
        available_credit = credit_limit - current_debt
        
        credit_limits.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'company_id': company['id'],
            'company_name': company['name'],
            'credit_limit': credit_limit,
            'monthly_limit': credit_limit / 2,
            'current_debt': current_debt,
            'available_credit': available_credit,
            'payment_terms_days': 30 if i == 0 else (60 if i == 1 else 45),
            'risk_level': 'critical' if current_debt > credit_limit else ('warning' if current_debt > credit_limit * 0.9 else 'normal'),
            'notes': f'Credit limit for {company["name"]}',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        })
    
    # Delete existing credit limits for this tenant
    await db.credit_limits.delete_many({'tenant_id': tenant_id})
    
    # Insert credit limits
    result = await db.credit_limits.insert_many(credit_limits)
    print(f"✅ Created {len(result.inserted_ids)} credit limits")
    
    # 3. Create Expenses
    print("\n💸 Creating Daily Expenses...")
    
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    expenses = []
    categories = ['Personnel', 'Utilities', 'Maintenance', 'Marketing', 'F&B Supplies', 'Housekeeping']
    departments = ['rooms', 'fnb', 'spa', 'laundry', 'other']
    
    for i in range(15):
        expense_date = today - timedelta(days=i)
        
        expenses.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'expense_number': f'EXP-{10000 + i}',
            'date': expense_date,
            'amount': 500 + (i * 150),
            'category': categories[i % len(categories)],
            'department': departments[i % len(departments)],
            'vendor': f'Vendor {i + 1}',
            'description': f'Sample expense for {categories[i % len(categories)]}',
            'payment_method': 'transfer' if i % 2 == 0 else 'cash',
            'paid': True if i % 3 != 0 else False,
            'approved_by': 'admin@hotel.com',
            'notes': f'Demo expense entry {i + 1}',
            'created_at': expense_date,
            'updated_at': expense_date
        })
    
    # Delete existing expenses for this tenant from last 30 days
    await db.expenses.delete_many({
        'tenant_id': tenant_id,
        'date': {'$gte': today - timedelta(days=30)}
    })
    
    # Insert expenses
    result = await db.expenses.insert_many(expenses)
    print(f"✅ Created {len(result.inserted_ids)} expenses")
    
    # 4. Create Cash Flow Entries
    print("\n💰 Creating Cash Flow Entries...")
    
    cash_flows = []
    
    # Inflows (payments received)
    for i in range(10):
        flow_date = today - timedelta(days=i)
        
        cash_flows.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'transaction_type': 'inflow',
            'amount': 1000 + (i * 200),
            'currency': 'TRY',
            'date': flow_date,
            'category': 'Room Payment' if i % 2 == 0 else 'F&B Payment',
            'reference_id': str(uuid.uuid4()),
            'reference_type': 'payment',
            'bank_account_id': banks[0]['id'] if i % 2 == 0 else banks[1]['id'],
            'description': f'Customer payment {i + 1}',
            'created_at': flow_date
        })
    
    # Outflows (expenses)
    for i in range(8):
        flow_date = today - timedelta(days=i)
        
        cash_flows.append({
            'id': str(uuid.uuid4()),
            'tenant_id': tenant_id,
            'transaction_type': 'outflow',
            'amount': 500 + (i * 100),
            'currency': 'TRY',
            'date': flow_date,
            'category': 'Operating Expense',
            'reference_id': str(uuid.uuid4()),
            'reference_type': 'expense',
            'bank_account_id': banks[0]['id'],
            'description': f'Vendor payment {i + 1}',
            'created_at': flow_date
        })
    
    # Delete existing cash flows for this tenant from last 30 days
    await db.cash_flow.delete_many({
        'tenant_id': tenant_id,
        'date': {'$gte': today - timedelta(days=30)}
    })
    
    # Insert cash flows
    result = await db.cash_flow.insert_many(cash_flows)
    print(f"✅ Created {len(result.inserted_ids)} cash flow entries")
    
    print("\n✅ Demo data creation complete!")
    print("\n📊 Summary:")
    print(f"   - Bank Accounts: {len(banks)}")
    print(f"   - Credit Limits: {len(credit_limits)}")
    print(f"   - Expenses: {len(expenses)}")
    print(f"   - Cash Flow Entries: {len(cash_flows)}")
    print("\n🎉 You can now test the Finance Mobile features!")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(create_demo_data())
