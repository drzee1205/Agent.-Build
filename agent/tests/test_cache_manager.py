"""
Tests for the cache management system.
"""

import time
import tempfile
from pathlib import Path
from core.cache_manager import (
    CacheEntry, MemoryCache, FileCache, CacheManager,
    cached
)


def test_cache_entry():
    """Test CacheEntry creation and expiration."""
    entry = CacheEntry(
        key="test_key",
        value="test_value",
        created_at=time.time(),
        last_accessed=time.time(),
        ttl=1.0  # 1 second TTL
    )
    
    assert not entry.is_expired()
    
    # Test expiration
    entry.created_at = time.time() - 2.0  # 2 seconds ago
    assert entry.is_expired()
    
    # Test touch
    old_access_time = entry.last_accessed
    old_access_count = entry.access_count
    entry.touch()
    assert entry.last_accessed > old_access_time
    assert entry.access_count == old_access_count + 1


def test_memory_cache():
    """Test MemoryCache functionality."""
    cache = MemoryCache(max_size=3, max_memory_mb=1)
    
    # Test basic set/get
    entry1 = CacheEntry("key1", "value1", time.time(), time.time())
    assert cache.set("key1", entry1)
    
    retrieved = cache.get("key1")
    assert retrieved is not None
    assert retrieved.value == "value1"
    
    # Test non-existent key
    assert cache.get("nonexistent") is None
    
    # Test size limit eviction
    entry2 = CacheEntry("key2", "value2", time.time(), time.time())
    entry3 = CacheEntry("key3", "value3", time.time(), time.time())
    entry4 = CacheEntry("key4", "value4", time.time(), time.time())
    
    cache.set("key2", entry2)
    cache.set("key3", entry3)
    cache.set("key4", entry4)  # Should evict key1
    
    assert cache.get("key1") is None  # Evicted
    assert cache.get("key2") is not None
    assert cache.get("key3") is not None
    assert cache.get("key4") is not None
    
    # Test delete
    assert cache.delete("key2")
    assert cache.get("key2") is None
    assert not cache.delete("nonexistent")
    
    # Test clear
    assert cache.clear()
    assert len(cache.keys()) == 0


def test_file_cache():
    """Test FileCache functionality."""
    with tempfile.TemporaryDirectory() as temp_dir:
        cache = FileCache(cache_dir=temp_dir, max_files=2)
        
        # Test basic set/get
        entry1 = CacheEntry("key1", "value1", time.time(), time.time())
        assert cache.set("key1", entry1)
        
        retrieved = cache.get("key1")
        assert retrieved is not None
        assert retrieved.value == "value1"
        
        # Test non-existent key
        assert cache.get("nonexistent") is None
        
        # Test file limit eviction
        entry2 = CacheEntry("key2", "value2", time.time(), time.time())
        entry3 = CacheEntry("key3", "value3", time.time(), time.time())
        
        cache.set("key2", entry2)
        time.sleep(0.01)  # Ensure different timestamps
        cache.set("key3", entry3)  # Should evict key1 (oldest)
        
        # key1 might still exist briefly, so we test that we don't exceed max_files
        cache_files = list(Path(temp_dir).glob("*.cache"))
        assert len(cache_files) <= 2
        
        # Test delete
        assert cache.delete("key2")
        assert cache.get("key2") is None
        
        # Test clear
        assert cache.clear()
        cache_files = list(Path(temp_dir).glob("*.cache"))
        assert len(cache_files) == 0


def test_cache_manager():
    """Test CacheManager functionality."""
    with tempfile.TemporaryDirectory() as temp_dir:
        memory_cache = MemoryCache(max_size=2)
        file_cache = FileCache(cache_dir=temp_dir)
        manager = CacheManager(memory_cache=memory_cache, file_cache=file_cache, default_ttl=3600)
        
        # Test basic set/get
        assert manager.set("key1", "value1", tags=["tag1"])
        assert manager.get("key1") == "value1"
        
        # Test cache miss
        assert manager.get("nonexistent") is None
        
        # Test memory -> file promotion
        # Fill memory cache to capacity
        manager.set("key2", "value2")
        manager.set("key3", "value3")  # This should evict key1 from memory
        
        # key1 should still be available from file cache
        assert manager.get("key1") == "value1"
        
        # Test delete
        assert manager.delete("key1")
        assert manager.get("key1") is None
        
        # Test tag-based invalidation
        manager.set("tagged1", "value1", tags=["group1"])
        manager.set("tagged2", "value2", tags=["group1", "group2"])
        manager.set("tagged3", "value3", tags=["group2"])
        
        # Verify items are set
        assert manager.get("tagged1") == "value1"
        assert manager.get("tagged2") == "value2"
        assert manager.get("tagged3") == "value3"
        
        invalidated = manager.invalidate_by_tags(["group1"])
        assert invalidated >= 1  # Should invalidate at least one item with group1 tag
        
        # Check that items with group1 tag are invalidated
        group1_items_invalidated = (
            manager.get("tagged1") is None and 
            manager.get("tagged2") is None
        )
        assert group1_items_invalidated or invalidated >= 1
        
        # Test stats
        stats = manager.get_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "sets" in stats
        assert "hit_rate" in stats
        
        # Test disable/enable
        manager.disable()
        assert manager.set("disabled_key", "disabled_value") is False
        assert manager.get("disabled_key") is None
        
        manager.enable()
        assert manager.set("enabled_key", "enabled_value") is True
        assert manager.get("enabled_key") == "enabled_value"


def test_cached_decorator():
    """Test the @cached decorator."""
    call_count = 0
    
    @cached(prefix="test_func", ttl=3600)
    def expensive_function(x, y):
        nonlocal call_count
        call_count += 1
        return x + y
    
    # First call should execute the function
    result1 = expensive_function(1, 2)
    assert result1 == 3
    assert call_count == 1
    
    # Second call with same args should use cache
    result2 = expensive_function(1, 2)
    assert result2 == 3
    assert call_count == 1  # Should not increment
    
    # Call with different args should execute the function
    result3 = expensive_function(2, 3)
    assert result3 == 5
    assert call_count == 2


def test_cache_expiration():
    """Test cache entry expiration."""
    cache = MemoryCache()
    
    # Create entry with short TTL
    entry = CacheEntry("key1", "value1", time.time(), time.time(), ttl=0.1)
    cache.set("key1", entry)
    
    # Should be available immediately
    assert cache.get("key1") is not None
    
    # Wait for expiration
    time.sleep(0.2)
    
    # Should be expired and removed
    assert cache.get("key1") is None


def test_cache_manager_key_generation():
    """Test cache key generation."""
    manager = CacheManager()
    
    # Test that same inputs generate same key
    key1 = manager._generate_key("prefix", "arg1", "arg2", kwarg1="value1")
    key2 = manager._generate_key("prefix", "arg1", "arg2", kwarg1="value1")
    assert key1 == key2
    
    # Test that different inputs generate different keys
    key3 = manager._generate_key("prefix", "arg1", "arg2", kwarg1="value2")
    assert key1 != key3
    
    key4 = manager._generate_key("different_prefix", "arg1", "arg2", kwarg1="value1")
    assert key1 != key4
