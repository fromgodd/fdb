"""
FDB Client - Python client library for FDB (Fast Database)
Redis-like interface for connecting to FDB server
"""

import asyncio
import json
import logging
from typing import Any, Optional, List, Union
from contextlib import asynccontextmanager


logger = logging.getLogger('FDBClient')


class FDBClient:
    """Async FDB client with Redis-like interface"""
    
    def __init__(self, host: str = "localhost", port: int = 6380, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
    
    async def connect(self) -> bool:
        """Connect to FDB server"""
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout
            )
            self.connected = True
            logger.info(f"Connected to FDB server at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to FDB server: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from FDB server"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.connected = False
        logger.info("Disconnected from FDB server")
    
    async def _send_command(self, command: str) -> str:
        """Send command to server and get response"""
        if not self.connected:
            raise ConnectionError("Not connected to FDB server")
        
        try:
            # Send command
            self.writer.write(f"{command}\n".encode('utf-8'))
            await self.writer.drain()
            
            # Read response
            response = await asyncio.wait_for(
                self.reader.readline(),
                timeout=self.timeout
            )
            
            return response.decode('utf-8').strip()
        except Exception as e:
            logger.error(f"Command failed: {e}")
            raise
    
    async def set(self, key: str, value: Any) -> bool:
        """Set key-value pair"""
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value)
        else:
            value_str = str(value)
        
        response = await self._send_command(f"SET {key} {value_str}")
        return response == "OK"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        response = await self._send_command(f"GET {key}")
        
        if response == "NULL":
            return None
        
        # Try to parse as JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return response
    
    async def delete(self, key: str) -> bool:
        """Delete key"""
        response = await self._send_command(f"DEL {key}")
        return response == "1"
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        response = await self._send_command(f"EXISTS {key}")
        return response == "1"
    
    async def keys(self, pattern: str = "*") -> List[str]:
        """Get all keys matching pattern"""
        response = await self._send_command(f"KEYS {pattern}")
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return []
    
    async def dbsize(self) -> int:
        """Get database size"""
        response = await self._send_command("DBSIZE")
        try:
            return int(response)
        except ValueError:
            return 0
    
    async def flushdb(self) -> bool:
        """Clear all data"""
        response = await self._send_command("FLUSHDB")
        return response == "OK"
    
    async def ping(self) -> bool:
        """Ping server"""
        response = await self._send_command("PING")
        return response == "PONG"
    
    async def info(self) -> dict:
        """Get server info"""
        response = await self._send_command("INFO")
        info = {}
        for line in response.split():
            if ':' in line:
                key, value = line.split(':', 1)
                info[key] = value
        return info
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()


@asynccontextmanager
async def fdb_client(host: str = "localhost", port: int = 6380, timeout: float = 5.0):
    """Context manager for FDB client"""
    client = FDBClient(host, port, timeout)
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()


# Synchronous wrapper for easier usage
class FDBSyncClient:
    """Synchronous wrapper for FDB client"""
    
    def __init__(self, host: str = "localhost", port: int = 6380, timeout: float = 5.0):
        self.async_client = FDBClient(host, port, timeout)
        self.loop = None
    
    def _run_async(self, coro):
        """Run async function in sync context"""
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
        return self.loop.run_until_complete(coro)
    
    def connect(self) -> bool:
        """Connect to FDB server"""
        return self._run_async(self.async_client.connect())
    
    def disconnect(self):
        """Disconnect from FDB server"""
        return self._run_async(self.async_client.disconnect())
    
    def set(self, key: str, value: Any) -> bool:
        """Set key-value pair"""
        return self._run_async(self.async_client.set(key, value))
    
    def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        return self._run_async(self.async_client.get(key))
    
    def delete(self, key: str) -> bool:
        """Delete key"""
        return self._run_async(self.async_client.delete(key))
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        return self._run_async(self.async_client.exists(key))
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Get all keys matching pattern"""
        return self._run_async(self.async_client.keys(pattern))
    
    def dbsize(self) -> int:
        """Get database size"""
        return self._run_async(self.async_client.dbsize())
    
    def flushdb(self) -> bool:
        """Clear all data"""
        return self._run_async(self.async_client.flushdb())
    
    def ping(self) -> bool:
        """Ping server"""
        return self._run_async(self.async_client.ping())
    
    def info(self) -> dict:
        """Get server info"""
        return self._run_async(self.async_client.info())
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()
    
    def __del__(self):
        """Cleanup on destruction"""
        if self.loop and not self.loop.is_closed():
            self.loop.close()


# Example usage
async def async_example():
    """Example usage with async client"""
    print("🔥 FDB Async Client Example")
    print("=" * 30)
    
    # Using context manager
    async with fdb_client() as client:
        # Test connection
        if await client.ping():
            print("✅ Connected to FDB server")
        
        # Set some data
        await client.set("user:1", {"name": "Alice", "age": 30, "city": "NYC"})
        await client.set("user:2", {"name": "Bob", "age": 25, "city": "LA"})
        await client.set("counter", 42)
        await client.set("message", "Hello FDB!")
        
        # Get data
        user1 = await client.get("user:1")
        print(f"👤 User 1: {user1}")
        
        counter = await client.get("counter")
        print(f"🔢 Counter: {counter}")
        
        message = await client.get("message")
        print(f"💬 Message: {message}")
        
        # Check existence
        exists = await client.exists("user:1")
        print(f"🔍 User 1 exists: {exists}")
        
        # Get all keys
        all_keys = await client.keys()
        print(f"🗝️  All keys: {all_keys}")
        
        # Get database size
        size = await client.dbsize()
        print(f"📊 Database size: {size}")
        
        # Update counter
        await client.set("counter", 100)
        updated_counter = await client.get("counter")
        print(f"🔄 Updated counter: {updated_counter}")
        
        # Delete a key
        deleted = await client.delete("user:2")
        print(f"🗑️  Deleted user:2: {deleted}")
        
        # Final state
        final_keys = await client.keys()
        print(f"🏁 Final keys: {final_keys}")


def sync_example():
    """Example usage with sync client"""
    print("\n🔥 FDB Sync Client Example")
    print("=" * 30)
    
    # Using context manager
    with FDBSyncClient() as client:
        # Test connection
        if client.ping():
            print("✅ Connected to FDB server")
        
        # Set some data
        client.set("product:1", {"name": "Laptop", "price": 999.99, "stock": 10})
        client.set("product:2", {"name": "Mouse", "price": 29.99, "stock": 50})
        client.set("total_sales", 15000)
        
        # Get data
        laptop = client.get("product:1")
        print(f"💻 Laptop: {laptop}")
        
        sales = client.get("total_sales")
        print(f"💰 Total sales: ${sales}")
        
        # Get all products
        product_keys = client.keys("product:*")
        print(f"📦 Product keys: {product_keys}")
        
        # Get database info
        info = client.info()
        print(f"ℹ️  Server info: {info}")


if __name__ == "__main__":
    print("🚀 FDB Client Library Examples")
    print("=" * 40)
    print("Make sure FDB server is running on localhost:6380")
    print("Start server with: python fdb_server.py")
    print()
    
    # Run async example
    try:
        asyncio.run(async_example())
    except Exception as e:
        print(f"❌ Async example failed: {e}")
    
    # Run sync example
    try:
        sync_example()
    except Exception as e:
        print(f"❌ Sync example failed: {e}")