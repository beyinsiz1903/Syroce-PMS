#!/bin/bash
export HOTELRUNNER_TEST_MONGO_URL=mongodb://localhost:27017/hotelrunner_test
export MONGO_URL=mongodb://localhost:27017/hotelrunner_test
export DB_NAME=hotelrunner_test
export VITE_BACKEND_URL=http://localhost:8000
export PYTHONPATH=.

echo "Starting Backend Server..."
.venv/bin/uvicorn server:app --port 8000 > backend_test.log 2>&1 &
BACKEND_PID=$!

echo "Starting Mock Server..."
.venv/bin/python domains/channel_manager/providers/hotelrunner/mock_server.py > mock_test.log 2>&1 &
MOCK_PID=$!

echo "Waiting for servers to initialize..."
sleep 15

echo "Running pytest..."
.venv/bin/pytest tests/test_hotelrunner_parity.py tests/test_hotelrunner_webhook_signature.py -v
TEST_EXIT_CODE=$?

echo "Cleaning up..."
kill $BACKEND_PID
kill $MOCK_PID

exit $TEST_EXIT_CODE
