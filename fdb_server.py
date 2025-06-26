"""
FDB - Fast Database Server
High-Performance Key-Value Engine with TCP Server
Redis-compatible protocol with async operations
"""

import asyncio
import threading
import time
import pickle
import hashlib
import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, Callable, Union
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, validator


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('FDB')


@dataclass
class CacheEntry:
    value: Any
    timestamp: float
    dirty: bool = False
    access_count: int = 0


@dataclass 
class FDBConfig:
    data_dir: str = "./fdb_data"
    cache_size: int = 10000
    flush_interval: float = 5.0
    compression: bool = True
    max_workers: int = 4
    file_extension: str = ".fdb"
    # Server config
    host: str = "localhost"
    port: int = 6380
    max_connections: int = 100


class KeyValidator(BaseModel):
    key: str
    
    @validator('key')
    def validate_key(cls, v):
        if not v or len(v) > 256:
            raise ValueError("Key must be 1-256 characters")
        return v


@dataclass
class FDBEngine:
    config: FDBConfig = field(default_factory=FDBConfig)
    _cache: Dict[str, CacheEntry] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _executor: ThreadPoolExecutor = field(default=None)
    _flush_task: Optional[asyncio.Task] = field(default=None)
    _running: bool = field(default=False)
    
    def __post_init__(self):
        Path(self.config.data_dir).mkdir(parents=True, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_workers)
        self._running = True
        logger.info(f"FDB Engine initialized with data_dir: {self.config.data_dir}")
        
    async def start(self):
        """Initialize async components"""
        if not self._flush_task:
            self._flush_task = asyncio.create_task(self._periodic_flush())
            logger.info("FDB Engine started")
    
    async def stop(self):
        """Cleanup resources"""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
        await self.flush()
        self._executor.shutdown(wait=True)
        logger.info("FDB Engine stopped")
    
    def _get_file_path(self, key: str) -> Path:
        """Generate file path for key using hash distribution"""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        subdir = key_hash[:2]
        filename = f"{key_hash}{self.config.file_extension}"
        return Path(self.config.data_dir) / subdir / filename
    
    def _validate_key(self, key: str) -> str:
        """Validate key using Pydantic"""
        return KeyValidator(key=key).key
    
    async def set(self, key: str, value: Any) -> bool:
        """Set key-value pair (Redis SET command)"""
        key = self._validate_key(key)
        
        with self._lock:
            entry = CacheEntry(
                value=value,
                timestamp=time.time(),
                dirty=True,
                access_count=1
            )
            self._cache[key] = entry
            
            if len(self._cache) > self.config.cache_size:
                await self._evict_lru()
        
        return True
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key (Redis GET command)"""
        key = self._validate_key(key)
        
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                entry.access_count += 1
                return entry.value
        
        loop = asyncio.get_event_loop()
        value = await loop.run_in_executor(self._executor, self._load_from_disk, key)
        
        if value is not None:
            with self._lock:
                self._cache[key] = CacheEntry(
                    value=value,
                    timestamp=time.time(),
                    dirty=False,
                    access_count=1
                )
        
        return value
    
    async def delete(self, key: str) -> bool:
        """Delete key (Redis DEL command)"""
        key = self._validate_key(key)
        
        with self._lock:
            if key in self._cache:
                del self._cache[key]
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._remove_from_disk, key)
    
    async def exists(self, key: str) -> bool:
        """Check if key exists (Redis EXISTS command)"""
        key = self._validate_key(key)
        
        with self._lock:
            if key in self._cache:
                return True
        
        file_path = self._get_file_path(key)
        return file_path.exists()
    
    async def keys(self, pattern: str = "*") -> List[str]:
        """Get all keys matching pattern (Redis KEYS command)"""
        keys = set()
        
        with self._lock:
            keys.update(self._cache.keys())
        
        loop = asyncio.get_event_loop()
        disk_keys = await loop.run_in_executor(self._executor, self._scan_disk_keys)
        keys.update(disk_keys)
        
        if pattern == "*":
            return list(keys)
        
        import fnmatch
        return [k for k in keys if fnmatch.fnmatch(k, pattern)]
    
    async def dbsize(self) -> int:
        """Get database size (Redis DBSIZE command)"""
        keys = await self.keys()
        return len(keys)
    
    async def flushdb(self) -> bool:
        """Clear all data (Redis FLUSHDB command)"""
        with self._lock:
            self._cache.clear()
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._clear_disk)
    
    async def flush(self) -> int:
        """Flush dirty cache entries to disk"""
        dirty_count = 0
        
        with self._lock:
            dirty_entries = {k: v for k, v in self._cache.items() if v.dirty}
        
        if not dirty_entries:
            return 0
        
        loop = asyncio.get_event_loop()
        tasks = []
        
        for key, entry in dirty_entries.items():
            task = loop.run_in_executor(
                self._executor, 
                self._save_to_disk, 
                key, 
                entry.value
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        with self._lock:
            for key, result in zip(dirty_entries.keys(), results):
                if key in self._cache and not isinstance(result, Exception):
                    self._cache[key].dirty = False
                    dirty_count += 1
        
        return dirty_count
    
    def _save_to_disk(self, key: str, value: Any) -> bool:
        """Save single key-value to disk"""
        try:
            file_path = self._get_file_path(key)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'key': key,
                'value': value,
                'timestamp': time.time()
            }
            
            with open(file_path, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            return True
        except Exception as e:
            logger.error(f"Failed to save key {key}: {e}")
            return False
    
    def _load_from_disk(self, key: str) -> Optional[Any]:
        """Load single value from disk"""
        try:
            file_path = self._get_file_path(key)
            if not file_path.exists():
                return None
                
            with open(file_path, 'rb') as f:
                data = pickle.load(f)
                
            return data.get('value')
        except Exception as e:
            logger.error(f"Failed to load key {key}: {e}")
            return None
    
    def _remove_from_disk(self, key: str) -> bool:
        """Remove single file from disk"""
        try:
            file_path = self._get_file_path(key)
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to remove key {key}: {e}")
            return False
    
    def _scan_disk_keys(self) -> List[str]:
        """Scan all keys from disk"""
        keys = []
        try:
            data_path = Path(self.config.data_dir)
            for file_path in data_path.rglob(f"*{self.config.file_extension}"):
                try:
                    with open(file_path, 'rb') as f:
                        data = pickle.load(f)
                        if 'key' in data:
                            keys.append(data['key'])
                except Exception:
                    continue
        except Exception:
            pass
        return keys
    
    def _clear_disk(self) -> bool:
        """Clear all disk files"""
        try:
            import shutil
            data_path = Path(self.config.data_dir)
            if data_path.exists():
                shutil.rmtree(data_path)
                data_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to clear disk: {e}")
            return False
    
    async def _evict_lru(self):
        """Evict least recently used cache entries"""
        if len(self._cache) <= self.config.cache_size:
            return
            
        sorted_items = sorted(
            self._cache.items(),
            key=lambda x: (x[1].access_count, x[1].timestamp)
        )
        
        to_remove = len(sorted_items) // 10 + 1
        
        for key, entry in sorted_items[:to_remove]:
            if entry.dirty:
                await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    self._save_to_disk,
                    key,
                    entry.value
                )
            del self._cache[key]
    
    async def _periodic_flush(self):
        """Periodic flush task"""
        while self._running:
            try:
                await asyncio.sleep(self.config.flush_interval)
                flushed = await self.flush()
                if flushed > 0:
                    logger.debug(f"Periodic flush: {flushed} entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic flush error: {e}")
                continue


class FDBProtocol:
    """Simple FDB protocol handler"""
    
    def __init__(self, db: FDBEngine):
        self.db = db
    
    async def parse_command(self, data: str) -> str:
        """Parse and execute FDB commands"""
        try:
            parts = data.strip().split()
            if not parts:
                return "ERROR: Empty command"
            
            cmd = parts[0].upper()
            
            if cmd == "SET" and len(parts) >= 3:
                key = parts[1]
                value = " ".join(parts[2:])
                try:
                    # Try to parse as JSON for complex objects
                    value = json.loads(value)
                except json.JSONDecodeError:
                    # Keep as string if not JSON
                    pass
                
                success = await self.db.set(key, value)
                return "OK" if success else "ERROR"
            
            elif cmd == "GET" and len(parts) == 2:
                key = parts[1]
                value = await self.db.get(key)
                if value is None:
                    return "NULL"
                
                if isinstance(value, (dict, list)):
                    return json.dumps(value)
                return str(value)
            
            elif cmd == "DEL" and len(parts) == 2:
                key = parts[1]
                success = await self.db.delete(key)
                return "1" if success else "0"
            
            elif cmd == "EXISTS" and len(parts) == 2:
                key = parts[1]
                exists = await self.db.exists(key)
                return "1" if exists else "0"
            
            elif cmd == "KEYS":
                pattern = parts[1] if len(parts) > 1 else "*"
                keys = await self.db.keys(pattern)
                return json.dumps(keys)
            
            elif cmd == "DBSIZE":
                size = await self.db.dbsize()
                return str(size)
            
            elif cmd == "FLUSHDB":
                success = await self.db.flushdb()
                return "OK" if success else "ERROR"
            
            elif cmd == "PING":
                return "PONG"
            
            elif cmd == "INFO":
                cache_size = len(self.db._cache)
                return f"cache_entries:{cache_size}"
            
            else:
                return f"ERROR: Unknown command '{cmd}'"
                
        except Exception as e:
            logger.error(f"Command parsing error: {e}")
            return f"ERROR: {str(e)}"


class FDBServer:
    """FDB TCP Server"""
    
    def __init__(self, config: Optional[FDBConfig] = None):
        self.config = config or FDBConfig()
        self.db = FDBEngine(self.config)
        self.protocol = FDBProtocol(self.db)
        self.server = None
        self.clients = set()
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle client connection"""
        client_addr = writer.get_extra_info('peername')
        logger.info(f"New client connected: {client_addr}")
        self.clients.add(writer)
        
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                
                message = data.decode('utf-8').strip()
                if not message:
                    continue
                
                logger.debug(f"Received from {client_addr}: {message}")
                
                response = await self.protocol.parse_command(message)
                response_data = f"{response}\n".encode('utf-8')
                
                writer.write(response_data)
                await writer.drain()
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Client {client_addr} error: {e}")
        finally:
            self.clients.discard(writer)
            writer.close()
            await writer.wait_closed()
            logger.info(f"Client {client_addr} disconnected")
    
    async def start(self):
        """Start FDB server"""
        await self.db.start()
        
        self.server = await asyncio.start_server(
            self.handle_client,
            self.config.host,
            self.config.port
        )
        
        logger.info(f"FDB Server started on {self.config.host}:{self.config.port}")
        logger.info(f"Data directory: {self.config.data_dir}")
        logger.info(f"Cache size: {self.config.cache_size}")
        
        async with self.server:
            await self.server.serve_forever()
    
    async def stop(self):
        """Stop FDB server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        # Close all client connections
        for writer in self.clients.copy():
            writer.close()
            await writer.wait_closed()
        
        await self.db.stop()
        logger.info("FDB Server stopped")


def create_engine(config: Optional[FDBConfig] = None) -> FDBEngine:
    """Create and return new FDB engine instance"""
    return FDBEngine(config or FDBConfig())


def create_server(config: Optional[FDBConfig] = None) -> FDBServer:
    """Create and return new FDB server instance"""
    return FDBServer(config or FDBConfig())


async def main():
    """Main server entry point"""
    config = FDBConfig(
        host="0.0.0.0",  # Listen on all interfaces
        port=6380,
        data_dir="./fdb_data",
        cache_size=10000,
        flush_interval=5.0
    )
    
    server = create_server(config)
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await server.stop()


if __name__ == "__main__":
    print("🚀 FDB - Fast Database Server")
    print("=" * 40)
    print(f"Starting server on localhost:6380")
    print("Press Ctrl+C to stop")
    print("=" * 40)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 FDB Server stopped")