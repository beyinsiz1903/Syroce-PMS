#!/bin/bash
echo "Starting backend..."
cd backend
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi
MONGO_DISABLE_TRANSACTIONS=1 TESTING=1 JWT_SECRET=dummy STRICT_JWT_SECRET=0 python3 -m uvicorn server:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

echo "Starting frontend..."
cd ../frontend
npm run preview > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo "Waiting for services to start..."
sleep 15

export E2E_BASE_URL=http://localhost:3000
export E2E_ADMIN_EMAIL=demo@hotel.com
export E2E_ADMIN_PASSWORD=demo123
export E2E_STRESS_TENANT_ID=bb306859-9748-430f-b24a-5a0d0ea29309

echo "Running tests..."
npm run test:e2e:business -- "$@"
TEST_EXIT_CODE=$?

echo "Tests finished with exit code $TEST_EXIT_CODE. Cleaning up..."
kill $BACKEND_PID
kill $FRONTEND_PID

exit $TEST_EXIT_CODE
