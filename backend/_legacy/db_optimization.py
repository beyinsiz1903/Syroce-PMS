"""
Database Optimization Script
Creates indexes and optimizes MongoDB for high-load hotel PMS
Target: 550 rooms, 300+ daily transactions, 1+ year operation
"""

from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def create_indexes():
    """Create comprehensive indexes for all collections"""
    
    mongo_url = os.environ['MONGO_URL']
    db_name = os.environ['DB_NAME']
    
    # Configure connection pool for high concurrency
    client = AsyncIOMotorClient(
        mongo_url,
        maxPoolSize=200,  # High concurrency support
        minPoolSize=20,   # Always maintain minimum connections
        maxIdleTimeMS=60000,  # Keep idle connections for 60s
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
        retryWrites=True,
        retryReads=True
    )
    
    db = client[db_name]
    
    print("🚀 Starting Database Optimization...")
    print("📊 Target: 550 rooms, 300+ daily transactions")
    print("🎯 Optimizing for 1+ year continuous operation\n")
    
    # ============= BOOKINGS COLLECTION =============
    print("📌 Creating indexes for BOOKINGS collection...")
    bookings = db.bookings
    
    # Most frequently queried fields
    await bookings.create_index([("tenant_id", 1), ("status", 1)])
    await bookings.create_index([("tenant_id", 1), ("check_in", 1)])
    await bookings.create_index([("tenant_id", 1), ("check_out", 1)])
    await bookings.create_index([("tenant_id", 1), ("room_id", 1)])
    await bookings.create_index([("tenant_id", 1), ("guest_id", 1)])
    await bookings.create_index([("tenant_id", 1), ("booking_id", 1)], unique=True)
    
    # Date range queries (critical for occupancy reports)
    await bookings.create_index([("tenant_id", 1), ("check_in", 1), ("check_out", 1)])
    await bookings.create_index([("tenant_id", 1), ("check_in", 1), ("status", 1)])
    await bookings.create_index([("tenant_id", 1), ("check_out", 1), ("status", 1)])
    
    # Company/corporate bookings
    await bookings.create_index([("tenant_id", 1), ("company_id", 1)])
    
    # Compound index for dashboard queries
    await bookings.create_index([
        ("tenant_id", 1), 
        ("status", 1), 
        ("check_in", 1)
    ])
    
    # Created at for historical queries
    await bookings.create_index([("tenant_id", 1), ("created_at", -1)])
    
    print("✅ Bookings indexes created")
    
    # ============= ROOMS COLLECTION =============
    print("📌 Creating indexes for ROOMS collection...")
    rooms = db.rooms
    
    await rooms.create_index([("tenant_id", 1), ("room_number", 1)], unique=True)
    await rooms.create_index([("tenant_id", 1), ("status", 1)])
    await rooms.create_index([("tenant_id", 1), ("room_type", 1)])
    await rooms.create_index([("tenant_id", 1), ("floor", 1)])
    await rooms.create_index([("tenant_id", 1), ("current_booking_id", 1)])
    
    # Compound for housekeeping board
    await rooms.create_index([("tenant_id", 1), ("status", 1), ("floor", 1)])
    
    print("✅ Rooms indexes created")
    
    # ============= GUESTS COLLECTION =============
    print("📌 Creating indexes for GUESTS collection...")
    guests = db.guests
    
    await guests.create_index([("tenant_id", 1), ("guest_id", 1)], unique=True)
    await guests.create_index([("tenant_id", 1), ("email", 1)])
    await guests.create_index([("tenant_id", 1), ("phone", 1)])
    await guests.create_index([("tenant_id", 1), ("passport_number", 1)])
    await guests.create_index([("tenant_id", 1), ("vip_status", 1)])
    await guests.create_index([("tenant_id", 1), ("blacklist_status", 1)])
    
    # Text search for name search
    await guests.create_index([("name", "text"), ("surname", "text")])
    
    print("✅ Guests indexes created")
    
    # ============= FOLIOS COLLECTION =============
    print("📌 Creating indexes for FOLIOS collection...")
    folios = db.folios
    
    await folios.create_index([("tenant_id", 1), ("folio_number", 1)], unique=True)
    await folios.create_index([("tenant_id", 1), ("booking_id", 1)])
    await folios.create_index([("tenant_id", 1), ("status", 1)])
    await folios.create_index([("tenant_id", 1), ("folio_type", 1)])
    await folios.create_index([("tenant_id", 1), ("created_at", -1)])
    
    # For balance queries
    await folios.create_index([("tenant_id", 1), ("status", 1), ("balance", 1)])
    
    print("✅ Folios indexes created")
    
    # ============= FOLIO_CHARGES COLLECTION =============
    print("📌 Creating indexes for FOLIO_CHARGES collection...")
    charges = db.folio_charges
    
    await charges.create_index([("tenant_id", 1), ("folio_id", 1)])
    await charges.create_index([("tenant_id", 1), ("charge_category", 1)])
    await charges.create_index([("tenant_id", 1), ("voided", 1)])
    await charges.create_index([("tenant_id", 1), ("created_at", -1)])
    
    # Compound for folio detail view
    await charges.create_index([("tenant_id", 1), ("folio_id", 1), ("voided", 1)])
    
    print("✅ Folio charges indexes created")
    
    # ============= PAYMENTS COLLECTION =============
    print("📌 Creating indexes for PAYMENTS collection...")
    payments = db.payments
    
    await payments.create_index([("tenant_id", 1), ("folio_id", 1)])
    await payments.create_index([("tenant_id", 1), ("payment_method", 1)])
    await payments.create_index([("tenant_id", 1), ("payment_type", 1)])
    await payments.create_index([("tenant_id", 1), ("created_at", -1)])
    
    print("✅ Payments indexes created")
    
    # ============= HOUSEKEEPING_TASKS COLLECTION =============
    print("📌 Creating indexes for HOUSEKEEPING_TASKS collection...")
    hk_tasks = db.housekeeping_tasks
    
    await hk_tasks.create_index([("tenant_id", 1), ("status", 1)])
    await hk_tasks.create_index([("tenant_id", 1), ("room_id", 1)])
    await hk_tasks.create_index([("tenant_id", 1), ("assigned_to", 1)])
    await hk_tasks.create_index([("tenant_id", 1), ("task_type", 1)])
    await hk_tasks.create_index([("tenant_id", 1), ("created_at", -1)])
    
    # For staff performance queries
    await hk_tasks.create_index([
        ("tenant_id", 1), 
        ("assigned_to", 1), 
        ("status", 1)
    ])
    
    # For timing analysis
    await hk_tasks.create_index([
        ("tenant_id", 1), 
        ("completed_at", -1)
    ])
    
    print("✅ Housekeeping tasks indexes created")
    
    # ============= AUDIT_LOGS COLLECTION =============
    print("📌 Creating indexes for AUDIT_LOGS collection...")
    audit_logs = db.audit_logs
    
    await audit_logs.create_index([("tenant_id", 1), ("timestamp", -1)])
    await audit_logs.create_index([("tenant_id", 1), ("user_id", 1)])
    await audit_logs.create_index([("tenant_id", 1), ("action", 1)])
    await audit_logs.create_index([("tenant_id", 1), ("entity_type", 1)])
    
    # TTL index - auto-delete logs older than 2 years
    await audit_logs.create_index([("timestamp", 1)], expireAfterSeconds=63072000)  # 2 years
    
    print("✅ Audit logs indexes created")
    
    # ============= ACCOUNTING_INVOICES COLLECTION =============
    print("📌 Creating indexes for ACCOUNTING_INVOICES collection...")
    invoices = db.accounting_invoices
    
    await invoices.create_index([("tenant_id", 1), ("invoice_number", 1)], unique=True)
    await invoices.create_index([("tenant_id", 1), ("status", 1)])
    await invoices.create_index([("tenant_id", 1), ("invoice_type", 1)])
    await invoices.create_index([("tenant_id", 1), ("issue_date", -1)])
    await invoices.create_index([("tenant_id", 1), ("customer_id", 1)])
    
    print("✅ Accounting invoices indexes created")
    
    # ============= COMPANIES COLLECTION =============
    print("📌 Creating indexes for COMPANIES collection...")
    companies = db.companies
    
    await companies.create_index([("tenant_id", 1), ("corporate_code", 1)], unique=True)
    await companies.create_index([("tenant_id", 1), ("status", 1)])
    await companies.create_index([("tenant_id", 1), ("name", 1)])
    
    # Text search for company search
    await companies.create_index([("name", "text")])
    
    print("✅ Companies indexes created")
    
    # ============= NOTIFICATIONS COLLECTION =============
    print("📌 Creating indexes for NOTIFICATIONS collection...")
    notifications = db.notifications
    
    await notifications.create_index([("tenant_id", 1), ("user_id", 1)])
    await notifications.create_index([("tenant_id", 1), ("read", 1)])
    await notifications.create_index([("tenant_id", 1), ("created_at", -1)])
    
    # Compound for unread notifications query
    await notifications.create_index([
        ("tenant_id", 1), 
        ("user_id", 1), 
        ("read", 1)
    ])
    
    # TTL index - auto-delete notifications older than 90 days
    await notifications.create_index([("created_at", 1)], expireAfterSeconds=7776000)  # 90 days
    
    print("✅ Notifications indexes created")
    
    # ============= USERS COLLECTION =============
    print("📌 Creating indexes for USERS collection...")
    users = db.users
    
    await users.create_index([("tenant_id", 1), ("email", 1)], unique=True)
    await users.create_index([("tenant_id", 1), ("role", 1)])
    await users.create_index([("tenant_id", 1), ("active", 1)])
    
    print("✅ Users indexes created")
    
    # ============= POS_ORDERS COLLECTION =============
    print("📌 Creating indexes for POS_ORDERS collection...")
    pos_orders = db.pos_orders
    
    await pos_orders.create_index([("tenant_id", 1), ("booking_id", 1)])
    await pos_orders.create_index([("tenant_id", 1), ("order_date", -1)])
    await pos_orders.create_index([("tenant_id", 1), ("status", 1)])
    
    print("✅ POS orders indexes created")
    
    # ============= MAINTENANCE_TASKS COLLECTION =============
    print("📌 Creating indexes for MAINTENANCE_TASKS collection...")
    maintenance = db.maintenance_tasks
    
    await maintenance.create_index([("tenant_id", 1), ("status", 1)])
    await maintenance.create_index([("tenant_id", 1), ("room_id", 1)])
    await maintenance.create_index([("tenant_id", 1), ("priority", 1)])
    await maintenance.create_index([("tenant_id", 1), ("created_at", -1)])
    
    print("✅ Maintenance tasks indexes created")
    
    # ============= APPROVALS COLLECTION =============
    print("📌 Creating indexes for APPROVALS collection...")
    approvals = db.approvals
    
    await approvals.create_index([("tenant_id", 1), ("status", 1)])
    await approvals.create_index([("tenant_id", 1), ("approval_type", 1)])
    await approvals.create_index([("tenant_id", 1), ("requested_by", 1)])
    await approvals.create_index([("tenant_id", 1), ("created_at", -1)])
    
    print("✅ Approvals indexes created")
    
    # ============= RATE_OVERRIDE_LOGS COLLECTION =============
    print("📌 Creating indexes for RATE_OVERRIDE_LOGS collection...")
    rate_logs = db.rate_override_logs
    
    await rate_logs.create_index([("tenant_id", 1), ("booking_id", 1)])
    await rate_logs.create_index([("tenant_id", 1), ("user_id", 1)])
    await rate_logs.create_index([("tenant_id", 1), ("timestamp", -1)])
    
    print("✅ Rate override logs indexes created")
    
    # ============= FEEDBACK COLLECTION =============
    print("📌 Creating indexes for FEEDBACK collection...")
    feedback = db.feedback
    
    await feedback.create_index([("tenant_id", 1), ("booking_id", 1)])
    await feedback.create_index([("tenant_id", 1), ("rating", 1)])
    await feedback.create_index([("tenant_id", 1), ("created_at", -1)])
    
    print("✅ Feedback indexes created")
    
    print("\n" + "="*60)
    print("✨ Database Optimization Complete!")
    print("="*60)
    print("✅ All indexes created successfully")
    print("✅ Connection pool optimized (maxPoolSize: 200, minPoolSize: 20)")
    print("✅ TTL indexes set for auto-cleanup (audit logs: 2 years, notifications: 90 days)")
    print("🚀 System ready for high-load operation (550 rooms, 300+ daily transactions)")
    print("="*60)
    
    # List all indexes for verification
    print("\n📊 Index Verification:")
    collections = [
        'bookings', 'rooms', 'guests', 'folios', 'folio_charges', 
        'payments', 'housekeeping_tasks', 'audit_logs', 'accounting_invoices',
        'companies', 'notifications', 'users', 'pos_orders', 'maintenance_tasks',
        'approvals', 'rate_override_logs', 'feedback'
    ]
    
    for coll_name in collections:
        coll = db[coll_name]
        indexes = await coll.index_information()
        print(f"  {coll_name}: {len(indexes)} indexes")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(create_indexes())
