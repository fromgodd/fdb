"""
FDB Usage Examples
Comprehensive examples showing how to use FDB as Redis replacement
"""

import asyncio
import time
import json
from fdb_server import create_engine, create_server, FDBConfig
from fdb_client import FDBClient, FDBSyncClient, fdb_client


# Example 1: Basic Database Operations
async def basic_operations_example():
    """Basic CRUD operations with FDB"""
    print("🔧 Example 1: Basic Database Operations")
    print("-" * 40)
    
    # Create engine instance (embedded mode)
    config = FDBConfig(data_dir="./example_db", cache_size=1000)
    db = create_engine(config)
    await db.start()
    
    try:
        # Create
        await db.set("user:john", {"name": "John Doe", "email": "john@example.com", "age": 30})
        await db.set("user:jane", {"name": "Jane Smith", "email": "jane@example.com", "age": 28})
        await db.set("settings:theme", "dark")
        await db.set("counter:visits", 1000)
        
        # Read
        user_john = await db.get("user:john")
        theme = await db.get("settings:theme")
        visits = await db.get("counter:visits")
        
        print(f"👤 John: {user_john}")
        print(f"🎨 Theme: {theme}")
        print(f"📊 Visits: {visits}")
        
        # Update
        await db.set("counter:visits", visits + 1)
        await db.set("user:john", {**user_john, "age": 31})
        
        # Check existence
        exists = await db.exists("user:john")
        print(f"🔍 User John exists: {exists}")
        
        # List keys
        user_keys = await db.keys("user:*")
        print(f"👥 User keys: {user_keys}")
        
        # Delete
        deleted = await db.delete("settings:theme")
        print(f"🗑️  Deleted theme: {deleted}")
        
        # Database size
        size = await db.dbsize()
        print(f"📏 Database size: {size} keys")
        
    finally:
        await db.stop()


# Example 2: Client-Server Mode
async def client_server_example():
    """Using FDB in client-server mode"""
    print("\n🌐 Example 2: Client-Server Mode")
    print("-" * 40)
    
    async with fdb_client() as client:
        # Test connection
        if not await client.ping():
            print("❌ Cannot connect to FDB server")
            return
        
        print("✅ Connected to FDB server")
        
        # Store different data types
        await client.set("string_key", "Hello FDB!")
        await client.set("number_key", 42)
        await client.set("float_key", 3.14159)
        await client.set("bool_key", True)
        await client.set("list_key", [1, 2, 3, "four", 5.0])
        await client.set("dict_key", {
            "name": "FDB",
            "type": "NoSQL",
            "features": ["fast", "persistent", "async"]
        })
        
        # Retrieve and display
        for key in ["string_key", "number_key", "float_key", "bool_key", "list_key", "dict_key"]:
            value = await client.get(key)
            print(f"🔑 {key}: {value} ({type(value).__name__})")


# Example 3: E-commerce Application
async def ecommerce_example():
    """E-commerce use case with FDB"""
    print("\n🛒 Example 3: E-commerce Application")
    print("-" * 40)
    
    async with fdb_client() as client:
        if not await client.ping():
            print("❌ Server not available")
            return
        
        # Clear previous data
        await client.flushdb()
        
        # Products catalog
        products = [
            {"id": "p1", "name": "Gaming Laptop", "price": 1299.99, "stock": 5, "category": "electronics"},
            {"id": "p2", "name": "Wireless Mouse", "price": 49.99, "stock": 25, "category": "electronics"},
            {"id": "p3", "name": "Coffee Mug", "price": 12.99, "stock": 100, "category": "home"},
            {"id": "p4", "name": "Programming Book", "price": 39.99, "stock": 15, "category": "books"}
        ]
        
        # Store products
        for product in products:
            await client.set(f"product:{product['id']}", product)
            await client.set(f"category:{product['category']}:{product['id']}", product['id'])
        
        # Store user data
        users = [
            {"id": "u1", "name": "Alice Johnson", "email": "alice@example.com", "balance": 500.00},
            {"id": "u2", "name": "Bob Wilson", "email": "bob@example.com", "balance": 1000.00}
        ]
        
        for user in users:
            await client.set(f"user:{user['id']}", user)
        
        # Shopping cart operations
        cart_u1 = {"user_id": "u1", "items": [{"product_id": "p1", "quantity": 1}, {"product_id": "p2", "quantity": 2}]}
        await client.set("cart:u1", cart_u1)
        
        # Order processing
        order = {
            "id": "order_001",
            "user_id": "u1",
            "items": cart_u1["items"],
            "total": 1399.97,
            "status": "pending",
            "timestamp": time.time()
        }
        await client.set(f"order:{order['id']}", order)
        
        # Query operations
        print("📦 Products in electronics category:")
        electronics_keys = await client.keys("category:electronics:*")
        for key in electronics_keys:
            product_id = await client.get(key)
            product = await client.get(f"product:{product_id}")
            print(f"  - {product['name']}: ${product['price']}")
        
        print(f"\n🛍️  User cart:")
        cart = await client.get("cart:u1")
        total = 0
        for item in cart["items"]:
            product = await client.get(f"product:{item['product_id']}")
            item_total = product["price"] * item["quantity"]
            total += item_total
            print(f"  - {product['name']} x{item['quantity']}: ${item_total:.2f}")
        print(f"💰 Cart total: ${total:.2f}")


# Example 4: Session Management
async def session_management_example():
    """Session management system using FDB"""
    print("\n🔐 Example 4: Session Management")
    print("-" * 40)
    
    async with fdb_client() as client:
        if not await client.ping():
            print("❌ Server not available")
            return
        
        # Simulate user login
        session_data = {
            "user_id": "user123",
            "username": "john_doe",
            "email": "john@example.com",
            "login_time": time.time(),
            "permissions": ["read", "write", "delete"],
            "preferences": {"theme": "dark", "language": "en"}
        }
        
        session_id = "sess_abc123xyz"
        await client.set(f"session:{session_id}", session_data)
        
        # Session validation
        stored_session = await client.get(f"session:{session_id}")
        if stored_session:
            print(f"✅ Valid session for user: {stored_session['username']}")
            print(f"🕐 Login time: {time.ctime(stored_session['login_time'])}")
            print(f"🔑 Permissions: {stored_session['permissions']}")
        
        # Update session (last activity)
        stored_session["last_activity"] = time.time()
        await client.set(f"session:{session_id}", stored_session)
        
        # Session cleanup (logout)
        await client.delete(f"session:{session_id}")
        print("🚪 Session logged out and cleaned up")


# Example 5: Caching Layer
async def caching_example():
    """Using FDB as a caching layer"""
    print("\n⚡ Example 5: Caching Layer")
    print("-" * 40)
    
    async with fdb_client() as client:
        if not await client.ping():
            print("❌ Server not available")
            return
        
        async def expensive_computation(x):
            """Simulate expensive computation"""
            await asyncio.sleep(0.1)  # Simulate delay
            return x ** 2 + 2 * x + 1
        
        async def cached_computation(x):
            """Cached version of expensive computation"""
            cache_key = f"compute:{x}"
            
            # Check cache first
            cached_result = await client.get(cache_key)
            if cached_result is not None:
                print(f"🎯 Cache hit for {x}: {cached_result}")
                return cached_result
            
            # Compute and cache
            print(f"💻 Computing {x}...")
            result = await expensive_computation(x)
            await client.set(cache_key, result)
            print(f"💾 Cached result for {x}: {result}")
            return result
        
        # Test caching
        test_values = [5, 10, 5, 15, 10, 20]
        
        start_time = time.time()
        for val in test_values:
            result = await cached_computation(val)
        end_time = time.time()
        
        print(f"⏱️  Total time: {end_time - start_time:.3f}s")
        
        # Show cache contents
        cache_keys = await client.keys("compute:*")
        print(f"🗂️  Cached computations: {len(cache_keys)}")


# Example 6: Real-time Analytics
async def analytics_example():
    """Real-time analytics with FDB"""
    print("\n📊 Example 6: Real-time Analytics")
    print("-" * 40)
    
    async with fdb_client() as client:
        if not await client.ping():
            print("❌ Server not available")
            return
        
        # Initialize counters
        await client.set("analytics:page_views", 0)
        await client.set("analytics:unique_users", 0)
        await client.set("analytics:total_revenue", 0.0)
        
        # Simulate events
        events = [
            {"type": "page_view", "user": "user1", "page": "/home"},
            {"type": "page_view", "user": "user2", "page": "/products"},
            {"type": "purchase", "user": "user1", "amount": 29.99},
            {"type": "page_view", "user": "user1", "page": "/about"},
            {"type": "purchase", "user": "user3", "amount": 149.99},
            {"type": "page_view", "user": "user3", "page": "/contact"}
        ]
        
        unique_users = set()
        
        for event in events:
            if event["type"] == "page_view":
                # Increment page views
                current_views = await client.get("analytics:page_views") or 0
                await client.set("analytics:page_views", current_views + 1)
                
                # Track unique users
                unique_users.add(event["user"])
                await client.set("analytics:unique_users", len(unique_users))
                
                # Store user's last page
                await client.set(f"user_session:{event['user']}", event["page"])
                
            elif event["type"] == "purchase":
                # Update revenue
                current_revenue = await client.get("analytics:total_revenue") or 0.0
                await client.set("analytics:total_revenue", current_revenue + event["amount"])
                
                # Store purchase
                purchase_key = f"purchase:{event['user']}:{int(time.time())}"
                await client.set(purchase_key, event["amount"])
        
        # Display analytics
        page_views = await client.get("analytics:page_views")
        unique_users_count = await client.get("analytics:unique_users")
        total_revenue = await client.get("analytics:total_revenue")
        
        print(f"👀 Page views: {page_views}")
        print(f"👥 Unique users: {unique_users_count}")
        print(f"💰 Total revenue: ${total_revenue:.2f}")
        
        # Show user sessions
        print("\n🔍 User sessions:")
        session_keys = await client.keys("user_session:*")
        for key in session_keys:
            user = key.split(":")[-1]
            last_page = await client.get(key)
            print(f"  {user}: {last_page}")


# Example 7: Synchronous Usage
def sync_usage_example():
    """Example using synchronous client"""
    print("\n🔄 Example 7: Synchronous Usage")
    print("-" * 40)
    
    with FDBSyncClient() as client:
        if not client.ping():
            print("❌ Server not available")
            return
        
        # Simple key-value operations
        client.set("sync_test", "This is a synchronous operation")
        value = client.get("sync_test")
        print(f"📝 Sync value: {value}")
        
        # Batch operations
        data = {
            "config:app_name": "My App",
            "config:version": "1.0.0",
            "config:debug": True,
            "config:max_users": 1000
        }
        
        for key, val in data.items():
            client.set(key, val)
        
        # Read configuration
        print("\n⚙️  Application Configuration:")
        config_keys = client.keys("config:*")
        for key in config_keys:
            value = client.get(key)
            config_name = key.split(":")[-1]
            print(f"  {config_name}: {value}")


# Performance benchmark
async def performance_benchmark():
    """Performance benchmark comparing operations"""
    print("\n🏃 Performance Benchmark")
    print("-" * 40)
    
    async with fdb_client() as client:
        if not await client.ping():
            print("❌ Server not available")
            return
        
        # Clear database
        await client.flushdb()
        
        # Write benchmark
        print("📝 Write benchmark (1000 operations)...")
        start_time = time.time()
        
        tasks = []
        for i in range(1000):
            task = client.set(f"bench:write:{i}", f"value_{i}")
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        write_time = time.time() - start_time
        write_ops = 1000 / write_time
        
        print(f"   Time: {write_time:.3f}s")
        print(f"   Ops/sec: {write_ops:.0f}")
        
        # Read benchmark
        print("\n📖 Read benchmark (1000 operations)...")
        start_time = time.time()
        
        tasks = []
        for i in range(1000):
            task = client.get(f"bench:write:{i}")
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        read_time = time.time() - start_time
        read_ops = 1000 / read_time
        
        print(f"   Time: {read_time:.3f}s")
        print(f"   Ops/sec: {read_ops:.0f}")
        
        # Verify results
        successful_reads = sum(1 for r in results if r is not None)
        print(f"   Successful reads: {successful_reads}/1000")


# Main execution
async def run_all_examples():
    """Run all examples"""
    print("🚀 FDB Complete Usage Examples")
    print("=" * 50)
    
    try:
        # Embedded database examples
        await basic_operations_example()
        
        # Client-server examples (requires running server)
        print("\n" + "=" * 50)
        print("CLIENT-SERVER EXAMPLES")
        print("(Make sure FDB server is running: python fdb_server.py)")
        print("=" * 50)
        
        await client_server_example()
        await ecommerce_example()
        await session_management_example()
        await caching_example()
        await analytics_example()
        await performance_benchmark()
        
        # Sync example
        sync_usage_example()
        
        print("\n🎉 All examples completed successfully!")
        
    except Exception as e:
        print(f"❌ Example failed: {e}")
        print("Make sure FDB server is running for client-server examples")


if __name__ == "__main__":
    print("🔥 FDB Usage Examples")
    print("Choose an example to run:")
    print("1. All examples")
    print("2. Basic operations (embedded)")
    print("3. Client-server examples only")
    print("4. Performance benchmark")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        asyncio.run(run_all_examples())
    elif choice == "2":
        asyncio.run(basic_operations_example())
    elif choice == "3":
        async def client_examples():
            await client_server_example()
            await ecommerce_example() 
            await session_management_example()
            await caching_example()
            await analytics_example()
        asyncio.run(client_examples())
    elif choice == "4":
        asyncio.run(performance_benchmark())
    else:
        print("Invalid choice. Running all examples...")
        asyncio.run(run_all_examples())