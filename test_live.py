import requests

BASE_URL = "http://localhost:8000"
headers = {"Origin": "http://localhost"}
resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "a", "password": "b"}, headers=headers)
print("LOGIN POST (localhost):", resp.status_code, resp.text)

headers2 = {"Origin": "http://localhost:5173"}
resp2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "a", "password": "b"}, headers=headers2)
print("LOGIN POST (localhost:5173):", resp2.status_code, resp2.text)

