import sqlite3, httpx
from app.core.security import decrypt_provider_key

conn = sqlite3.connect('nova.db')
row = conn.execute("SELECT encrypted_api_key FROM ai_provider_settings WHERE provider='GROQ'").fetchone()
conn.close()

key = decrypt_provider_key(row[0])
print("Key length:", len(key))
print("Key:", key)

r = httpx.get(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": f"Bearer {key}"},
    timeout=15,
)
print("Status:", r.status_code)
if r.status_code == 200:
    ids = [m["id"] for m in r.json().get("data", [])]
    print("Models available:")
    for i in ids:
        print("  -", i)
else:
    print(r.text)
