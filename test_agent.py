import urllib.request
import json
import urllib.error

data = json.dumps({'message':'what is todays profit', 'trace_id':'test'}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8000/api/v1/agent/chat', data=data, headers={'Content-Type':'application/json'})
try:
    res = urllib.request.urlopen(req, timeout=30)
    print("SUCCESS:", res.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP ERROR:", e.code, e.read().decode())
except Exception as e:
    print("ERROR:", str(e))
