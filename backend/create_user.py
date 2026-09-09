import sqlite3
import bcrypt
import uuid

conn = sqlite3.connect('nova.db')
cursor = conn.cursor()

email = 'adejuwonbasit0@gmail.com'
password = 'baskid555'

hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
user_id = str(uuid.uuid4())

cursor.execute('''
    INSERT INTO users 
    (id, email, hashed_password, full_name, status, role, is_email_verified, assistant_name, created_at, updated_at) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
''', (user_id, email, hashed, 'Admin User', 'active', 'super_admin', 1, 'Nova'))

conn.commit()
print(f'User {email} created as super_admin!')
conn.close()
