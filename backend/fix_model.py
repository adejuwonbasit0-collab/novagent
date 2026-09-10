import sqlite3
conn = sqlite3.connect('nova.db')
cur = conn.cursor()
cur.execute("UPDATE ai_provider_settings SET model='openai/gpt-oss-120b' WHERE provider='GROQ'")
conn.commit()
print("rows updated:", cur.rowcount)
cur.execute("SELECT provider, model, enabled FROM ai_provider_settings")
for r in cur.fetchall():
    print(r)
conn.close()
