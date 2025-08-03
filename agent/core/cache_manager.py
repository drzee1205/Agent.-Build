"""
Advanced caching system for the agent.

This module provides multi-layer caching for LLM responses, generated code,
and other expensive operations with intelligent cache invalidation.
"""

import hashlib
import json
import time
import pickle
import os
from typing import Any, Dict, Optional, Callable, TypeVar, List
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from pathlib import Path
import threading
from collections import OrderedDict
from log import get_structured_logger

logger = get_structured_logger(__name__)

T = TypeVar('T')


@dataclass
class CacheEntry:
    """Individual cache entry with metadata."""
    key: str
    value: Any
    created_at: float
    last_accessed: float
    access_count: int = 0
    ttl: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    size_bytes: int = 0
    
    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        if self.ttl is None:
            return False
        return time.time() - self.created_at > self.ttl
    
    def touch(self):
        """Update last accessed time and increment access count."""
        self.last_accessed = time.time()
        self.access_count += 1


class CacheBackend(ABC):
    """Abstract base class for cache backends."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[CacheEntry]:
        """Get a cache entry by key."""
        pass
    
    @abstractmethod
    def set(self, key: str, entry: CacheEntry) -> bool:
        """Set a cache entry."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a cache entry."""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """Clear all cache entries."""
        pass
    
    @abstractmethod
    def keys(self) -> List[str]:
        """Get all cache keys."""
        pass


class MemoryCache(CacheBackend):
    """In-memory cache backend with LRU eviction."""
    
    def __init__(self, max_size: int = 1000, max_memory_mb: int = 100):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.current_memory_bytes = 0
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[CacheEntry]:
        with self._lock:
            entry = self.cache.get(key)
            if entry is None:
                return None
            
            if entry.is_expired():
                self.delete(key)
                return None
            
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            entry.touch()
            return entry
    
    def set(self, key: str, entry: CacheEntry) -> bool:
        with self._lock:
            # Calculate entry size
            try:
                entry.size_bytes = len(pickle.dumps(entry.value))
            except Exception:
                entry.size_bytes = len(str(entry.value).encode('utf-8'))
            
            # Remove existing entry if present
            if key in self.cache:
                old_entry = self.cache[key]
                self.current_memory_bytes -= old_entry.size_bytes
                del self.cache[key]
            
            # Check if we need to evict entries
            while (len(self.cache) >= self.max_size or 
                   self.current_memory_bytes + entry.size_bytes > self.max_memory_bytes):
                if not self.cache:
                    break
                oldest_key, oldest_entry = self.cache.popitem(last=False)
                self.current_memory_bytes -= oldest_entry.size_bytes
                logger.debug("Evicted cache entry", key=oldest_key, reason="size_limit")
            
            # Add new entry
            self.cache[key] = entry
            self.current_memory_bytes += entry.size_bytes
            return True
    
    def delete(self, key: str) -> bool:
        with self._lock:
            entry = self.cache.pop(key, None)
            if entry:
                self.current_memory_bytes -= entry.size_bytes
                return True
            return False
    
    def clear(self) -> bool:
        with self._lock:
            self.cache.clear()
            self.current_memory_bytes = 0
            return True
    
    def keys(self) -> List[str]:
        with self._lock:
            return list(self.cache.keys())


class FileCache(CacheBackend):
    """File-based persistent cache backend."""
    
    def __init__(self, cache_dir: str = ".cache", max_files: int = 10000):
        self.cache_dir = Path(cache_dir)
        self.max_files = max_files
        self.cache_dir.mkdir(exist_ok=True)
        self._lock = threading.RLock()
    
    def _get_file_path(self, key: str) -> Path:
        """Get file path for cache key."""
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{safe_key}.cache"
    
    def get(self, key: str) -> Optional[CacheEntry]:
        with self._lock:
            file_path = self._get_file_path(key)
            if not file_path.exists():
                return None
            
            try:
                with open(file_path, 'rb') as f:
                    entry = pickle.load(f)
                
                if entry.is_expired():
                    self.delete(key)
                    return None
                
                entry.touch()
                # Update file with new access info
                with open(file_path, 'wb') as f:
                    pickle.dump(entry, f)
                
                return entry
            except Exception as e:
                logger.error("Error reading cache file", key=key, error=str(e))
                return None
    
    def set(self, key: str, entry: CacheEntry) -> bool:
        with self._lock:
            file_path = self._get_file_path(key)
            
            try:
                # Check if we need to evict old files
                cache_files = list(self.cache_dir.glob("*.cache"))
                if len(cache_files) >= self.max_files:
                    # Sort by last modified time and remove oldest
                    cache_files.sort(key=lambda p: p.stat().st_mtime)
                    for old_file in cache_files[:len(cache_files) - self.max_files + 1]:
                        old_file.unlink(missing_ok=True)
                
                with open(file_path, 'wb') as f:
                    pickle.dump(entry, f)
                return True
            except Exception as e:
                logger.error("Error writing cache file", key=key, error=str(e))
                return False
    
    def delete(self, key: str) -> bool:
        with self._lock:
            file_path = self._get_file_path(key)
            try:
                file_path.unlink(missing_ok=True)
                return True
            except Exception as e:
                logger.error("Error deleting cache file", key=key, error=str(e))
                return False
    
    def clear(self) -> bool:
        with self._lock:
            try:
                for cache_file in self.cache_dir.glob("*.cache"):
                    cache_file.unlink()
                return True
            except Exception as e:
                logger.error("Error clearing cache", error=str(e))
                return False
    
    def keys(self) -> List[str]:
        # Note: This is expensive for file cache, use sparingly
        keys = []
        for cache_file in self.cache_dir.glob("*.cache"):
            try:
                with open(cache_file, 'rb') as f:
                    entry = pickle.load(f)
                    keys.append(entry.key)
            except Exception:
                continue
        return keys


class CacheManager:
    """Multi-layer cache manager with intelligent strategies."""
    
    def __init__(
        self,
        memory_cache: Optional[MemoryCache] = None,
        file_cache: Optional[FileCache] = None,
        default_ttl: Optional[float] = None
    ):
        self.memory_cache = memory_cache or MemoryCache()
        self.file_cache = file_cache
        self.default_ttl = default_ttl
        self.enabled = True
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'memory_hits': 0,
            'file_hits': 0
        }
        self._lock = threading.RLock()
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a cache key from arguments."""
        key_data = {
            'prefix': prefix,
            'args': args,
            'kwargs': sorted(kwargs.items()) if kwargs else {}
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.enabled:
            return None
        
        with self._lock:
            # Try memory cache first
            entry = self.memory_cache.get(key)
            if entry:
                self._stats['hits'] += 1
                self._stats['memory_hits'] += 1
                logger.debug("Cache hit (memory)", key=key[:16])
                return entry.value
            
            # Try file cache if available
            if self.file_cache:
                entry = self.file_cache.get(key)
                if entry:
                    # Promote to memory cache
                    self.memory_cache.set(key, entry)
                    self._stats['hits'] += 1
                    self._stats['file_hits'] += 1
                    logger.debug("Cache hit (file)", key=key[:16])
                    return entry.value
            
            self._stats['misses'] += 1
            logger.debug("Cache miss", key=key[:16])
            return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """Set value in cache."""
        if not self.enabled:
            return False
        
        with self._lock:
            ttl = ttl or self.default_ttl
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                last_accessed=time.time(),
                ttl=ttl,
                tags=tags or []
            )
            
            # Set in memory cache
            success = self.memory_cache.set(key, entry)
            
            # Set in file cache if available
            if self.file_cache:
                self.file_cache.set(key, entry)
            
            if success:
                self._stats['sets'] += 1
                logger.debug("Cache set", key=key[:16], ttl=ttl)
            
            return success
    
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        with self._lock:
            success = self.memory_cache.delete(key)
            if self.file_cache:
                self.file_cache.delete(key)
            
            if success:
                self._stats['deletes'] += 1
                logger.debug("Cache delete", key=key[:16])
            
            return success
    
    def clear(self) -> bool:
        """Clear all cache entries."""
        with self._lock:
            success = self.memory_cache.clear()
            if self.file_cache:
                self.file_cache.clear()
            
            logger.info("Cache cleared")
            return success
    
    def invalidate_by_tags(self, tags: List[str]) -> int:
        """Invalidate cache entries by tags."""
        if not self.enabled:
            return 0
        
        invalidated = 0
        keys_to_delete = []
        
        # Check memory cache
        for key in self.memory_cache.keys():
            entry = self.memory_cache.get(key)
            if entry and any(tag in entry.tags for tag in tags):
                keys_to_delete.append(key)
        
        # Delete found keys
        for key in keys_to_delete:
            if self.delete(key):
                invalidated += 1
        
        logger.info("Cache invalidated by tags", tags=tags, count=invalidated)
        return invalidated
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = self._stats['hits'] / total_requests if total_requests > 0 else 0
            
            return {
                **self._stats,
                'hit_rate': hit_rate,
                'memory_size': len(self.memory_cache.cache),
                'memory_bytes': self.memory_cache.current_memory_bytes,
                'enabled': self.enabled
            }
    
    def enable(self):
        """Enable caching."""
        self.enabled = True
        logger.info("Cache enabled")
    
    def disable(self):
        """Disable caching."""
        self.enabled = False
        logger.info("Cache disabled")


# Global cache manager instance
_cache_manager = CacheManager(
    file_cache=FileCache() if os.getenv('ENABLE_FILE_CACHE', 'false').lower() == 'true' else None,
    default_ttl=float(os.getenv('CACHE_DEFAULT_TTL', '3600'))  # 1 hour default
)


def get_cache_manager() -> CacheManager:
    """Get the global cache manager instance."""
    return _cache_manager


def cached(
    prefix: str,
    ttl: Optional[float] = None,
    tags: Optional[List[str]] = None,
    key_func: Optional[Callable[..., str]] = None
):
    """
    Decorator for caching function results.
    
    Args:
        prefix: Cache key prefix
        ttl: Time to live in seconds
        tags: Cache tags for invalidation
        key_func: Custom function to generate cache key
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = _cache_manager._generate_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_result = _cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            _cache_manager.set(cache_key, result, ttl=ttl, tags=tags)
            return result
        
        return wrapper
    return decorator


def cache_llm_response(
    prompt: str,
    model: str,
    response: str,
    ttl: Optional[float] = None
):
    """Cache an LLM response."""
    key = _cache_manager._generate_key("llm_response", prompt=prompt, model=model)
    _cache_manager.set(key, response, ttl=ttl, tags=["llm", model])


def get_cached_llm_response(prompt: str, model: str) -> Optional[str]:
    """Get cached LLM response."""
    key = _cache_manager._generate_key("llm_response", prompt=prompt, model=model)
    return _cache_manager.get(key)


def invalidate_llm_cache(model: Optional[str] = None):
    """Invalidate LLM cache entries."""
    tags = ["llm"]
    if model:
        tags.append(model)
    _cache_manager.invalidate_by_tags(tags)
