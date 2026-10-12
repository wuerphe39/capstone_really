import json
import platform
import socket

import requests

response = requests.get('http://127.0.0.1:18010/health', timeout=5)
response.raise_for_status()
print(json.dumps({'hostname': socket.gethostname(), 'architecture': platform.machine(),
                  'python': platform.python_version(), 'api_status': response.status_code,
                  'api_health': response.json()}, ensure_ascii=False))
