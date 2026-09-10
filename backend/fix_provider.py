import sqlite3
from app.core.security import encrypt_provider_key

new_key = "gsk_your_new_key_here"   # <-- paste new key
conn = sqlite3.connect('nova.db')
conn.execute(
    "UPDATE ai_provider_settings SET model=?, encrypted_api_key=?, enabled=1 WHERE provider='GROQ'",
    ("openai/gpt-oss-120b", encrypt_provider_key(new_key)),
)
conn.commit()
print("rows updated:", conn.total_changes)
conn.close()
