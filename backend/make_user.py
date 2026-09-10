import asyncio
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User

async def main():
    async with AsyncSessionLocal() as db:
        u = User(
            email='adejuwonbasit0@gmail.com',
            hashed_password=hash_password('baskid555'),
            full_name='Admin User',
            status='active',
            role='super_admin',
            is_email_verified=True,
            assistant_name='Nova',
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        print('Created user id:', u.id)

asyncio.run(main())
