
import requests
import json

keystone_url = "http://10.220.56.254:5000/v3/auth/tokens"
headers = {'Content-Type': 'application/json'}

data = {
    "auth": {
        "identity": {
            "methods": ["password"],
            "password": {
                "user": {
                    "name": "dingoops",
                    "domain": {"name": "default"},
                    "password": "dingoops@2024"
                }
            }
        }
    }
}

response = requests.post(keystone_url, headers=headers, data=json.dumps(data))
token = response.headers['X-Subject-Token']
print(f"Token: {token}")