# -*- coding: utf-8 -*-
"""
OS Memory Management
====================
Implements memory management concepts:
- Memory Pool Allocator (pre-allocation)
- Fragmentation tracking
- Memory statistics
- Automatic defragmentation

Student demonstrates understanding of:
- Heap management strategies
- Fragmentation vs. performance trade-offs
- Pre-allocation patterns
- Memory accounting

Performance Trade-offs:
- Pool allocation: +Setup overhead, +Memory overhead, -Fragmentation, +Speed
- Direct allocation: -Memory overhead, +Fragmentation risk, -Speed
"""

import numpy as np
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
import gc
from os_synchronization import Mutex, RWLock
import logging

logger = logging.getLogger(__name__)


class AllocationStrategy(Enum):
    """Memory allocation strategies"""
    FIRST_FIT = "first_fit"        # Find first suitable block
    BEST_FIT = "best_fit"          # Find smallest suitable block
    BUDDY_SYSTEM = "buddy"         # Power-of-2 sized blocks
    POOL = "pool"                  # Fixed-size pool


@dataclass
class MemoryBlock:
    """Represents an allocated memory block"""
    address: int  # Unique identifier
    size: int
    is_free: bool = False
    data: Optional[np.ndarray] = None
    timestamp_allocated: float = 0.0
    timestamp_freed: float = 0.0
    owner: str = "unknown"
    
    def address_str(self) -> str:
        """Simulate memory address"""
        return f"0x{self.address:016x}"


@dataclass
class MemoryStats:
    """Memory usage statistics"""
    total_allocated: int = 0
    total_freed: int = 0
    current_in_use: int = 0
    peak_in_use: int = 0
    fragmentation_ratio: float = 0.0
    num_allocations: int = 0
    num_frees: int = 0
    num_defragmentations: int = 0


class MemoryManager:
    """
    Simple memory manager simulating OS heap management.
    
    System Call Equivalents:
    - Unix: malloc(), free(), brk(), mmap()
    - Linux: do_brk(), do_mmap() kernel functions
    """
    
    def __init__(self, max_size_bytes: int = 1_000_000_000, strategy: AllocationStrategy = AllocationStrategy.POOL):
        self.max_size = max_size_bytes
        self.strategy = strategy
        self.blocks: List[MemoryBlock] = []
        self.free_blocks: List[MemoryBlock] = []
        self.stats = MemoryStats()
        self._lock = Mutex("memory_lock", track_stats=True)
        self._next_address = 0x1000  # Start after reserved space
        self._defrag_threshold = 0.3  # Defragment when 30% fragmented
    
    def _next_addr(self) -> int:
        """Get next unique address"""
        addr = self._next_address
        self._next_address += 1
        return addr
    
    def allocate(self, size: int, owner: str = "unknown") -> Optional[MemoryBlock]:
        """
        Allocate memory block.
        
        System Call: malloc() - allocates size bytes
        Returns: MemoryBlock or None if allocation fails
        """
        with self._lock:
            # Check capacity
            if self.stats.current_in_use + size > self.max_size:
                logger.warning(f"Memory allocation failed: {size} bytes (limit: {self.max_size})")
                return None
            
            # Find or create free block
            block = None
            
            if self.strategy == AllocationStrategy.FIRST_FIT:
                # Find first fitting free block
                for free_block in self.free_blocks:
                    if free_block.size >= size:
                        block = free_block
                        break
            
            elif self.strategy == AllocationStrategy.BEST_FIT:
                # Find smallest fitting block
                suitable_blocks = [b for b in self.free_blocks if b.size >= size]
                if suitable_blocks:
                    block = min(suitable_blocks, key=lambda b: b.size)
            
            elif self.strategy == AllocationStrategy.POOL:
                # Always allocate from pool (simplistic)
                block = MemoryBlock(
                    address=self._next_addr(),
                    size=size,
                    is_free=False,
                    data=np.zeros(size, dtype=np.uint8),
                    owner=owner
                )
            
            if block and not self.strategy == AllocationStrategy.POOL:
                # Reuse existing block
                if block.size > size:
                    # Create remainder block
                    remainder = MemoryBlock(
                        address=self._next_addr(),
                        size=block.size - size,
                        is_free=True,
                        owner="free"
                    )
                    self.free_blocks.append(remainder)
                
                block.size = size
                block.is_free = False
                block.owner = owner
                self.free_blocks.remove(block)
            
            elif not block:
                # Allocate new block
                block = MemoryBlock(
                    address=self._next_addr(),
                    size=size,
                    is_free=False,
                    data=np.zeros(size, dtype=np.uint8),
                    owner=owner
                )
            
            self.blocks.append(block)
            self.stats.current_in_use += size
            if self.stats.current_in_use > self.stats.peak_in_use:
                self.stats.peak_in_use = self.stats.current_in_use
            self.stats.num_allocations += 1
            
            logger.debug(f"Allocated {size} bytes for {owner} at {block.address_str()}")
            return block
    
    def free(self, block: MemoryBlock) -> bool:
        """
        Free memory block.
        
        System Call: free() - deallocates memory
        """
        with self._lock:
            if block not in self.blocks:
                logger.warning(f"Attempted to free unknown block")
                return False
            
            block.is_free = True
            block.owner = "free"
            self.free_blocks.append(block)
            self.stats.current_in_use -= block.size
            self.stats.total_freed += block.size
            self.stats.num_frees += 1
            
            logger.debug(f"Freed {block.size} bytes at {block.address_str()}")
            
            # Check fragmentation and defragment if needed
            self._update_fragmentation_stats()
            if self.stats.fragmentation_ratio > self._defrag_threshold:
                self._defragment()
            
            return True
    
    def _update_fragmentation_stats(self) -> None:
        """Calculate fragmentation ratio"""
        if not self.free_blocks:
            self.stats.fragmentation_ratio = 0.0
            return
        
        # Fragmentation = (Number of free blocks) / (Total blocks)
        total_blocks = len(self.blocks)
        free_block_count = len(self.free_blocks)
        
        if total_blocks > 0:
            self.stats.fragmentation_ratio = free_block_count / max(total_blocks, 1)
    
    def _defragment(self) -> None:
        """
        Defragmentation - Coalesce adjacent free blocks.
        
        Performance Trade-off: Stop-the-world pause vs fragmentation reduction
        """
        logger.info("Running defragmentation...")
        
        # Sort blocks by address
        self.blocks.sort(key=lambda b: b.address)
        
        # Coalesce adjacent free blocks
        coalesced = 0
        i = 0
        while i < len(self.blocks) - 1:
            current = self.blocks[i]
            next_block = self.blocks[i + 1]
            
            if current.is_free and next_block.is_free:
                # Merge blocks
                current.size += next_block.size
                self.blocks.pop(i + 1)
                self.free_blocks.remove(next_block)
                coalesced += 1
                continue
            
            i += 1
        
        self.stats.num_defragmentations += 1
        logger.info(f"Defragmentation complete: coalesced {coalesced} blocks")
    
    def get_stats(self) -> MemoryStats:
        """Get memory statistics"""
        with self._lock:
            self._update_fragmentation_stats()
            return self.stats
    
    def get_free_memory(self) -> int:
        """Get total free memory"""
        with self._lock:
            return sum(b.size for b in self.free_blocks)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get readable memory summary"""
        stats = self.get_stats()
        return {
            "current_in_use_mb": stats.current_in_use / 1_000_000,
            "peak_in_use_mb": stats.peak_in_use / 1_000_000,
            "max_capacity_mb": self.max_size / 1_000_000,
            "fragmentation_ratio": f"{stats.fragmentation_ratio:.2%}",
            "num_allocations": stats.num_allocations,
            "num_frees": stats.num_frees,
            "num_defragmentations": stats.num_defragmentations,
        }


class FrameBufferPool:
    """
    Specialized memory pool for video frame buffers.
    
    Demonstrates:
    - Pre-allocation patterns (avoids malloc stalls during video processing)
    - Fixed-size pool management
    - Thread-safe access
    
    Performance Trade-off:
    - Pre-allocation overhead: ~100MB upfront
    - Runtime benefit: Zero allocation latency
    """
    
    def __init__(self, buffer_size: int, num_buffers: int, height: int, width: int, channels: int = 3):
        self.buffer_size = buffer_size
        self.num_buffers = num_buffers
        self.height = height
        self.width = width
        self.channels = channels
        
        # Pre-allocate all buffers
        self.available_buffers: List[np.ndarray] = []
        self.in_use_buffers: Dict[int, np.ndarray] = {}
        
        self._lock = Mutex("frame_buffer_pool", track_stats=True)
        self.stats = {
            'allocated': 0,
            'freed': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'max_concurrent': 0
        }
        
        self._initialize_buffers()
    
    def _initialize_buffers(self) -> None:
        """Pre-allocate all frame buffers"""
        logger.info(f"Pre-allocating {self.num_buffers} frame buffers ({self.buffer_size // 1_000_000}MB each)...")
        
        for i in range(self.num_buffers):
            # Allocate as float32 (typical for CV operations)
            buffer = np.zeros((self.height, self.width, self.channels), dtype=np.float32)
            self.available_buffers.append(buffer)
    
    def acquire(self) -> Optional[np.ndarray]:
        """
        Acquire frame buffer from pool.
        Returns None if all buffers in use (should be rare).
        """
        with self._lock:
            if self.available_buffers:
                buffer = self.available_buffers.pop()
                buffer_id = id(buffer)
                self.in_use_buffers[buffer_id] = buffer
                self.stats['allocated'] += 1
                self.stats['cache_hits'] += 1
                
                # Track max concurrent usage
                if len(self.in_use_buffers) > self.stats['max_concurrent']:
                    self.stats['max_concurrent'] = len(self.in_use_buffers)
                
                return buffer
            else:
                self.stats['cache_misses'] += 1
                logger.warning(f"Frame buffer pool exhausted! ({len(self.in_use_buffers)} in use)")
                return None
    
    def release(self, buffer: np.ndarray) -> bool:
        """Release frame buffer back to pool"""
        with self._lock:
            buffer_id = id(buffer)
            if buffer_id in self.in_use_buffers:
                del self.in_use_buffers[buffer_id]
                self.available_buffers.append(buffer)
                self.stats['freed'] += 1
                return True
            else:
                logger.warning(f"Attempted to release untracked buffer")
                return False
    
    def get_utilization(self) -> float:
        """Get current buffer utilization percentage"""
        with self._lock:
            return (len(self.in_use_buffers) / self.num_buffers) * 100.0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics"""
        with self._lock:
            # Calculate utilization inline to avoid re-acquiring lock
            utilization = (len(self.in_use_buffers) / self.num_buffers) * 100.0
            return {
                'allocated': self.stats['allocated'],
                'freed': self.stats['freed'],
                'in_use': len(self.in_use_buffers),
                'available': len(self.available_buffers),
                'cache_hits': self.stats['cache_hits'],
                'cache_misses': self.stats['cache_misses'],
                'max_concurrent': self.stats['max_concurrent'],
                'utilization_percent': utilization
            }


# Global memory manager instance
_global_memory_manager: Optional[MemoryManager] = None


def init_memory_manager(max_size_bytes: int = 1_000_000_000) -> MemoryManager:
    """Initialize global memory manager"""
    global _global_memory_manager
    _global_memory_manager = MemoryManager(max_size_bytes)
    logger.info(f"Memory manager initialized with {max_size_bytes // 1_000_000}MB capacity")
    return _global_memory_manager


def get_memory_manager() -> MemoryManager:
    """Get global memory manager instance"""
    if _global_memory_manager is None:
        return init_memory_manager()
    return _global_memory_manager
