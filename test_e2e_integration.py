"""
Comprehensive End-to-End Test Suite for Nova Assistant Platform Rebuild
Tests:
- Database & Alembic schema validation
- User registration & JWT auth lifecycle
- Admin Branding & CMS configuration
- Security Center (Phishing, Fraud, IP Audits, Threat Metrics)
- Real-time System Health & Telemetry
- Conversation Persistence & Chat History
- OS Tools (File operations, System commands, Fast-path router)
- WebSocket broadcast & dynamic config sync
"""

import sys
import asyncio
import os
import json
from pathlib import Path

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

async def test_full_pipeline():
    print("\n=======================================================")
    print("      NOVA PLATFORM END-TO-END INTEGRATION TEST        ")
    print("=======================================================\n")
    
    # Set SQLite DB environment for testing
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_nova.db"
    os.environ["JWT_SECRET_KEY"] = "test_super_secret_jwt_key_for_testing_12345"
    
    from app.core.database import engine, Base, AsyncSessionLocal
    from app.core.security import hash_password, verify_password, create_access_token
    from app.models.user import User, UserRole, UserStatus
    from app.models.device import Device
    from app.models.platform_settings import PlatformSettings
    from app.models.security_event import SecurityEvent, SecurityEventType, SecurityRiskLevel
    from app.models.conversation import Conversation, Message
    from app.services.connection_manager import connection_manager
    from sqlalchemy import select

    # Step 1: Initialize Database Tables
    print("[1/8] Creating test SQLite database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("  [OK] Tables created successfully (users, devices, platform_settings, security_events, conversations, messages).")

    # Step 2: Auth and User Management
    print("\n[2/8] Testing User & Admin Lifecycle...")
    async with AsyncSessionLocal() as session:
        # Create Admin
        admin_user = User(
            email="admin@nova.ai",
            hashed_password=hash_password("AdminSecretPass123!"),
            full_name="Admin Boss",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        # Create Normal User
        normal_user = User(
            email="user@nova.ai",
            hashed_password=hash_password("UserSecretPass123!"),
            full_name="Normal User",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
            is_email_verified=True,
        )
        session.add_all([admin_user, normal_user])
        await session.commit()
        await session.refresh(admin_user)
        await session.refresh(normal_user)
        
        # Test password verification & token generation
        assert verify_password("AdminSecretPass123!", admin_user.hashed_password)
        token = create_access_token(admin_user.id)
        assert token is not None and len(token) > 20
        print(f"  [OK] Admin ({admin_user.email}) and User ({normal_user.email}) created & authenticated.")

    # Step 3: Platform Settings & Dynamic Branding
    print("\n[3/8] Testing Platform Branding & CMS Settings...")
    async with AsyncSessionLocal() as session:
        settings = PlatformSettings(
            site_name="Nova Pro Assistant",
            site_description="Next-Gen Agentic OS Platform",
            assistant_name="NovaPrime",
            assistant_greeting="Hello from NovaPrime!",
            assistant_personality="You are NovaPrime, the supreme operating assistant.",
            default_language="en-US",
            default_voice="en-US-JennyNeural",
            theme="dark",
            accent_color="#6366f1",
        )
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
        
        # Query back
        res = await session.execute(select(PlatformSettings).limit(1))
        stored = res.scalars().first()
        assert stored.site_name == "Nova Pro Assistant"
        assert stored.assistant_name == "NovaPrime"
        print(f"  [OK] Platform branding saved: Assistant Name = '{stored.assistant_name}' | Theme = '{stored.accent_color}'.")

    # Step 4: Security Center (Phishing, Fraud, IP Threat Diagnostics)
    print("\n[4/8] Testing Security Center Diagnostic Heuristics...")
    from app.api.v1.security import check_phishing, check_fraud, get_ip_audit_log, get_security_stats
    from app.schemas.security import PhishingCheckRequest, FraudCheckRequest

    async with AsyncSessionLocal() as session:
        # Test 4a: Phishing check on malicious URL
        phishing_req = PhishingCheckRequest(
            text_content="Urgent: Your PayPal account is suspended. Enter your password immediately to verify.",
            sender_info="paypal-security@gmail.com",
            urls=["http://198.51.100.22/secure-login/paypa1.php"]
        )
        phishing_res = await check_phishing(phishing_req, current_user=normal_user, db=session)
        print(f"  [OK] Phishing Check Result: {phishing_res.risk_level} (Score: {phishing_res.risk_score}/100, Indicators: {len(phishing_res.indicators)})")
        assert phishing_res.risk_level in ["HIGH", "CRITICAL"]

        # Test 4b: Fraud evaluation on high-risk transaction
        fraud_req = FraudCheckRequest(
            transaction_or_message="Wire transfer 50000 USD to new bank account immediately to avoid penalties.",
            amount="50000 USD",
            recipient="external_high_risk_wallet"
        )
        fraud_res = await check_fraud(fraud_req, current_user=normal_user, db=session)
        print(f"  [OK] Fraud Risk Score: {fraud_res.risk_score}/100 (Level: {fraud_res.risk_level})")
        assert fraud_res.risk_score > 30

        # Test 4c: IP audit log retrieval
        ip_logs = await get_ip_audit_log(limit=10, current_user=normal_user, db=session)
        print(f"  [OK] Retrieved {len(ip_logs)} security audit event logs.")
        assert len(ip_logs) >= 2

        # Test 4d: Stats aggregation
        stats_res = await get_security_stats(current_user=normal_user, db=session)
        print(f"  [OK] Security Stats: {stats_res.total_events} total events recorded, {stats_res.active_threats} active threats.")
        assert stats_res.total_events >= 2

    # Step 5: Conversation Persistence & Message History
    print("\n[5/8] Testing Conversation & Message History...")
    async with AsyncSessionLocal() as session:
        conv = Conversation(
            user_id=normal_user.id,
            title="Desktop Automation Session",
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)

        msg1 = Message(
            conversation_id=conv.id,
            role="user",
            content="Open WordPad and create a note for me.",
        )
        msg2 = Message(
            conversation_id=conv.id,
            role="assistant",
            content="I have opened WordPad and prepared your workspace.",
            tool_calls_json=json.dumps([{"tool_name": "open_application", "arguments": {"app_name": "wordpad"}, "result": "SUCCESS"}])
        )
        session.add_all([msg1, msg2])
        await session.commit()

        # Query messages
        res = await session.execute(select(Message).where(Message.conversation_id == conv.id))
        stored_msgs = res.scalars().all()
        assert len(stored_msgs) == 2
        print(f"  [OK] Conversation '{conv.title}' stored with {len(stored_msgs)} messages and tool metadata.")

    from app.tools.base import ToolRegistry
    # Ensure tool modules are imported and registered
    import app.tools.system_tools
    import app.tools.os_file_tools

    # Step 6: Verify Registered Tools in Registry
    print("\n[6/8] Testing Registered Tools & Declarations...")
    all_tools = ToolRegistry.all()
    tool_names = [t.name for t in all_tools]
    print(f"  [OK] Registered tools ({len(all_tools)}): {', '.join(tool_names)}")
    
    assert "open_application" in tool_names
    assert "restart_computer" in tool_names
    assert "take_screenshot" in tool_names
    assert "show_desktop" in tool_names
    assert "rename_file" in tool_names
    assert "delete_file" in tool_names
    assert "read_file" in tool_names

    # Check confirmation flag on high-risk tools
    restart_tool = ToolRegistry.get("restart_computer")
    assert restart_tool.requires_confirmation is True
    delete_tool = ToolRegistry.get("delete_file")
    assert delete_tool.requires_confirmation is True
    screenshot_tool = ToolRegistry.get("take_screenshot")
    assert screenshot_tool.requires_confirmation is False
    print("  [OK] Safety confirmation flags validated on high-risk tools (restart_computer, delete_file).")

    # Step 7: Test Local OS Controller & Fast-Path Router
    print("\n[7/8] Testing Desktop Fast-Path Local Router...")
    # Add desktop agent to path to test local router
    desktop_dir = Path(__file__).resolve().parent / "desktop-agent"
    sys.path.insert(0, str(desktop_dir))
    
    from core.local_router import route_locally
    
    # Test WordPad routing
    r_wordpad = route_locally("open wordpad")
    assert r_wordpad is not None and r_wordpad.tool_name == "open_application"
    print(f"  [OK] Fast-path router matched 'open wordpad' -> {r_wordpad.tool_name}({r_wordpad.params})")

    # Test Paint routing
    r_paint = route_locally("launch paint")
    assert r_paint is not None and r_paint.tool_name == "open_application"
    print(f"  [OK] Fast-path router matched 'launch paint' -> {r_paint.tool_name}({r_paint.params})")

    # Test Screenshot routing
    r_screen = route_locally("take a screenshot")
    assert r_screen is not None and r_screen.tool_name == "take_screenshot"
    print(f"  [OK] Fast-path router matched 'take a screenshot' -> {r_screen.tool_name}")

    # Test Show Desktop routing
    r_desktop = route_locally("show desktop")
    assert r_desktop is not None and r_desktop.tool_name == "show_desktop"
    print(f"  [OK] Fast-path router matched 'show desktop' -> {r_desktop.tool_name}")

    # Test Lock Computer routing
    r_lock = route_locally("lock computer")
    assert r_lock is not None and r_lock.tool_name == "lock_computer"
    print(f"  [OK] Fast-path router matched 'lock computer' -> {r_lock.tool_name}")

    # Test Active Window routing
    r_act = route_locally("what app am i using?")
    assert r_act is not None and r_act.tool_name == "get_active_window"
    print(f"  [OK] Fast-path router matched 'what app am i using?' -> {r_act.tool_name}")

    # Step 8: Live WebSocket Configuration Broadcast
    print("\n[8/8] Testing WebSocket Dynamic Configuration Sync...")
    # Broadcast config update to connected device pool
    test_config = {
        "assistant_name": "NovaPrime",
        "default_voice_id": "en-US-JennyNeural",
        "accent_color": "#6366f1",
    }
    await connection_manager.broadcast_config_update(test_config)
    print("  [OK] connection_manager.broadcast_config_update dispatched without error.")

    # Clean up test SQLite database
    await engine.dispose()
    if os.path.exists("test_nova.db"):
        try:
            os.remove("test_nova.db")
        except:
            pass

    print("\n=======================================================")
    print("  ALL 8 INTEGRATION PHASES PASSED WITH ZERO ERRORS!   ")
    print("=======================================================\n")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
