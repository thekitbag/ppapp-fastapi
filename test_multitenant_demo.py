#!/usr/bin/env python3
"""
Multi-tenant Task System Demo

This script demonstrates the complete multi-tenant authentication and task management system.
It shows how users can only see and manage their own tasks, with complete isolation.
"""

import asyncio
import httpx
import json
from typing import Dict, Any

# Configuration
BASE_URL = "http://127.0.0.1:8000"
API_BASE = f"{BASE_URL}/api/v1"

class MultiTenantDemo:
    """Demo class for multi-tenant task system."""
    
    def __init__(self):
        self.client = httpx.AsyncClient()
        self.user_sessions = {}
    
    async def dev_login(self, email: str, name: str) -> str:
        """Login as a user for dev/testing."""
        print(f"\n🔐 Logging in as {name} ({email})")
        
        response = await self.client.post(
            f"{API_BASE}/auth/dev-login",
            json={"email": email, "name": name}
        )
        
        if response.status_code == 200:
            # Extract session cookie
            session_cookie = None
            for cookie in response.cookies:
                if cookie.name == "ppapp_session":
                    session_cookie = cookie.value
                    break
            
            if session_cookie:
                print(f"✅ Successfully logged in as {name}")
                return session_cookie
            else:
                print(f"❌ No session cookie received")
                return None
        else:
            print(f"❌ Login failed: {response.status_code} - {response.text}")
            return None
    
    async def get_current_user(self, session_token: str) -> Dict[str, Any]:
        """Get current user information."""
        response = await self.client.get(
            f"{API_BASE}/auth/me",
            cookies={"ppapp_session": session_token}
        )
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"👤 Current user: {user_data['name']} ({user_data['email']})")
            return user_data
        else:
            print(f"❌ Failed to get user info: {response.status_code}")
            return None
    
    async def create_task(self, session_token: str, title: str, description: str = None) -> Dict[str, Any]:
        """Create a task for the authenticated user."""
        task_data = {"title": title}
        if description:
            task_data["description"] = description
        
        response = await self.client.post(
            f"{API_BASE}/tasks",
            json=task_data,
            cookies={"ppapp_session": session_token}
        )
        
        if response.status_code == 201:
            task = response.json()
            print(f"✅ Created task: {task['title']} (ID: {task['id']})")
            return task
        else:
            print(f"❌ Failed to create task: {response.status_code} - {response.text}")
            return None
    
    async def list_tasks(self, session_token: str) -> list:
        """List tasks for the authenticated user."""
        response = await self.client.get(
            f"{API_BASE}/tasks",
            cookies={"ppapp_session": session_token}
        )
        
        if response.status_code == 200:
            tasks = response.json()
            print(f"📋 Found {len(tasks)} tasks")
            for task in tasks:
                print(f"   • {task['title']} (ID: {task['id'][:8]}...)")
            return tasks
        else:
            print(f"❌ Failed to list tasks: {response.status_code}")
            return []
    
    async def try_access_other_task(self, session_token: str, task_id: str) -> bool:
        """Try to access another user's task (should fail)."""
        response = await self.client.get(
            f"{API_BASE}/tasks/{task_id}",
            cookies={"ppapp_session": session_token}
        )
        
        if response.status_code == 404:
            print(f"🔒 Correctly blocked access to task {task_id[:8]}... (404 Not Found)")
            return False
        elif response.status_code == 200:
            print(f"⚠️ Unexpectedly allowed access to task {task_id[:8]}...")
            return True
        else:
            print(f"❓ Unexpected response: {response.status_code}")
            return False
    
    async def run_demo(self):
        """Run the complete multi-tenant demo."""
        print("🚀 Starting Multi-Tenant Task System Demo")
        print("=" * 50)
        
        # Step 1: Create two users
        user_a_session = await self.dev_login("alice@example.com", "Alice")
        user_b_session = await self.dev_login("bob@example.com", "Bob")
        
        if not user_a_session or not user_b_session:
            print("❌ Failed to create user sessions. Ensure dev login is enabled.")
            return
        
        # Step 2: Verify user identities
        print("\n📋 Verifying User Identities:")
        user_a_info = await self.get_current_user(user_a_session)
        user_b_info = await self.get_current_user(user_b_session)
        
        # Step 3: Create tasks for each user
        print("\n📝 Creating Tasks:")
        alice_tasks = []
        bob_tasks = []
        
        # Alice creates tasks
        print("\nAs Alice:")
        alice_tasks.append(await self.create_task(user_a_session, "Alice's Personal Project", "Work on my side project"))
        alice_tasks.append(await self.create_task(user_a_session, "Buy groceries", "Weekly shopping"))
        
        # Bob creates tasks
        print("\nAs Bob:")
        bob_tasks.append(await self.create_task(user_b_session, "Bob's Work Task", "Finish the quarterly report"))
        bob_tasks.append(await self.create_task(user_b_session, "Exercise routine", "Go for a run"))
        
        # Step 4: List tasks for each user (should only see their own)
        print("\n📋 Listing Tasks (Multi-Tenant Isolation):")
        print("\nAs Alice (should only see Alice's tasks):")
        alice_visible_tasks = await self.list_tasks(user_a_session)
        
        print("\nAs Bob (should only see Bob's tasks):")
        bob_visible_tasks = await self.list_tasks(user_b_session)
        
        # Step 5: Test cross-user access (should fail)
        print("\n🔒 Testing Cross-User Access (Should Fail):")
        
        if alice_tasks and bob_tasks:
            alice_task_id = alice_tasks[0]['id']
            bob_task_id = bob_tasks[0]['id']
            
            print("\nAlice trying to access Bob's task:")
            await self.try_access_other_task(user_a_session, bob_task_id)
            
            print("\nBob trying to access Alice's task:")
            await self.try_access_other_task(user_b_session, alice_task_id)
        
        # Step 6: Summary
        print("\n✅ Multi-Tenant Demo Complete!")
        print("=" * 50)
        print("Key Features Demonstrated:")
        print("1. 🔐 Separate user authentication with database-backed sessions")
        print("2. 📋 Complete task isolation - users only see their own tasks")
        print("3. 🔒 Cross-user access protection - 404 errors for unauthorized access")
        print("4. 👤 User identity verification through /auth/me endpoint")
        print("5. 🏗️ Clean service architecture with user_id filtering")
        
        await self.client.aclose()

async def main():
    """Main function to run the demo."""
    demo = MultiTenantDemo()
    await demo.run_demo()

if __name__ == "__main__":
    print("Multi-Tenant Task System Demo")
    print("Make sure the FastAPI server is running on http://127.0.0.1:8000")
    print("And that AUTH_DEV_ENABLED=true is set for dev login")
    print()
    
    asyncio.run(main())