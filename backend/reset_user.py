import sqlite3
conn = sqlite3.connect('nova.db')
conn.execute("DELETE FROM users WHERE email='adejuwonbasit0@gmail.com'")
conn.commit()
print('deleted')
conn.close()
