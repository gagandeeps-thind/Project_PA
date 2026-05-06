import requests

try:
    response = requests.post("http://localhost:8000/api/v1/auth/login", json={
        "email": "test@test.com",
        "password": "password",
        "device_timestamp": "2026-05-06T00:00:00Z"
    })
    print(response.status_code)
    print(response.text)
except Exception as e:
    print(e)
