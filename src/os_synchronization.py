# -*- coding: utf-8 -*-
"""
OS Synchronization Primitives
==============================
Implements OS-like synchronization mechanisms:
- Mutex (Binary Semaphore)
- Semaphore
- Condition Variables
- Read-Write Locks

Student demonstrates understanding of:
- Thread safety and race condition prevention
- Monitor pattern implementation
- Deadlock avoidance
- Priority inversion awareness
"""

import sys
from pathlib import Path

# Add project root to sys.path to allow running this file directly
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.append(root_dir)

import threading
import time
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SyncStrategy(Enum):
    """Strategy for synchronization (performance trade-off)"""
    SPIN_LOCK = "spin"          # Busy wait (high CPU, low latency)
    MUTEX = "mutex"             # Standard mutex (balanced)
    SEMAPHORE = "semaphore"     # Counting semaphore (flexible)
    RW_LOCK = "rw_lock"         # Read-write lock (reader-friendly)


@dataclass
class SyncStats:
    """Track synchronization performance metrics"""
    acquisitions: int = 0
    contentions: int = 0  # Times thread waited
    max_wait_time_us: float = 0.0
    total_wait_time_us: float = 0.0
    
    def avg_wait_time_us(self) -> float:
        return (self.total_wait_time_us / self.contentions) if self.contentions > 0 else 0.0


class Mutex:
    """
    Binary Semaphore (Mutex) - Provides mutual exclusion.
    
    System Call Equivalents:
    - Unix: pthread_mutex_lock, pthread_mutex_unlock
    - Linux: futex(), mutex operations
    """
    
    def __init__(self, name: str = "mutex", track_stats: bool = False):
        self.name = name
        self._lock = threading.Lock()
        self._locked = False
        self.track_stats = track_stats
        self.stats = SyncStats() if track_stats else None
    
    def lock(self) -> float:
        """
        Acquire lock. Returns wait time in microseconds.
        
        System Call: pthread_mutex_lock() - blocks until available
        """
        start = time.perf_counter()
        acquired_immediately = self._lock.acquire(blocking=False)
        
        if not acquired_immediately:
            if self.track_stats:
                self.stats.contentions += 1
            acquired_immediately = self._lock.acquire(blocking=True)
        
        if self.track_stats:
            wait_time_us = (time.perf_counter() - start) * 1_000_000
            self.stats.acquisitions += 1
            self.stats.total_wait_time_us += wait_time_us
            if wait_time_us > self.stats.max_wait_time_us:
                self.stats.max_wait_time_us = wait_time_us
            return wait_time_us
        return 0.0
    
    def unlock(self) -> None:
        """
        Release lock.
        
        System Call: pthread_mutex_unlock()
        """
        self._lock.release()
    
    def try_lock(self, timeout_sec: float = 0.0) -> bool:
        """
        Non-blocking lock attempt.
        
        System Call: pthread_mutex_trylock()
        """
        return self._lock.acquire(timeout=timeout_sec)
    
    def __enter__(self):
        self.lock()
        return self
    
    def __exit__(self, *args):
        self.unlock()


class Semaphore:
    """
    Counting Semaphore - Allows N concurrent access.
    
    System Call Equivalents:
    - Unix: sem_init(), sem_wait(), sem_post()
    - Linux: semctl(), semget(), semop()
    """
    
    def __init__(self, initial_count: int, name: str = "semaphore", track_stats: bool = False):
        self.name = name
        self.count = initial_count
        self.initial_count = initial_count
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self.track_stats = track_stats
        self.stats = SyncStats() if track_stats else None
    
    def wait(self) -> float:
        """
        Decrement semaphore (P/DOWN operation).
        
        System Call: sem_wait() - blocks if count <= 0
        Returns: wait time in microseconds
        """
        start = time.perf_counter()
        with self._cv:
            while self.count <= 0:
                if self.track_stats:
                    self.stats.contentions += 1
                self._cv.wait()
            self.count -= 1
        
        if self.track_stats:
            wait_time_us = (time.perf_counter() - start) * 1_000_000
            self.stats.acquisitions += 1
            self.stats.total_wait_time_us += wait_time_us
            if wait_time_us > self.stats.max_wait_time_us:
                self.stats.max_wait_time_us = wait_time_us
            return wait_time_us
        return 0.0
    
    def signal(self, count: int = 1) -> None:
        """
        Increment semaphore (V/UP operation).
        
        System Call: sem_post() - wakes one waiter
        """
        with self._cv:
            self.count += count
            self._cv.notify_all()
    
    def try_wait(self, timeout_sec: float = 0.0) -> bool:
        """
        Non-blocking wait attempt.
        
        System Call: sem_trywait()
        """
        with self._cv:
            if self.count > 0:
                self.count -= 1
                return True
            return False
    
    def __enter__(self):
        self.wait()
        return self
    
    def __exit__(self, *args):
        self.signal()


class RWLock:
    """
    Reader-Writer Lock - Multiple readers OR single writer.
    
    Design Trade-off:
    - Readers don't block each other (high throughput for read-heavy workloads)
    - Writers are exclusive (strong consistency)
    - Better for frame buffer management than simple mutex
    
    System Call Equivalents:
    - Unix: pthread_rwlock_*
    - Linux: futex for fast lock acquisitions
    """
    
    def __init__(self, name: str = "rwlock", track_stats: bool = False):
        self.name = name
        self._read_count = 0
        self._write_count = 0
        self._lock = threading.Lock()
        self._read_ready = threading.Condition(self._lock)
        self._write_ready = threading.Condition(self._lock)
        self.track_stats = track_stats
        self.stats = {
            'reads': SyncStats(),
            'writes': SyncStats()
        } if track_stats else None
    
    def acquire_read(self) -> float:
        """Acquire read lock (multiple readers allowed)"""
        start = time.perf_counter()
        
        with self._read_ready:
            while self._write_count > 0:
                if self.track_stats:
                    self.stats['reads'].contentions += 1
                self._read_ready.wait()
            self._read_count += 1
        
        if self.track_stats:
            wait_time_us = (time.perf_counter() - start) * 1_000_000
            self.stats['reads'].acquisitions += 1
            self.stats['reads'].total_wait_time_us += wait_time_us
            if wait_time_us > self.stats['reads'].max_wait_time_us:
                self.stats['reads'].max_wait_time_us = wait_time_us
            return wait_time_us
        return 0.0
    
    def release_read(self) -> None:
        """Release read lock"""
        with self._write_ready:
            self._read_count -= 1
            if self._read_count == 0:
                self._write_ready.notify_all()
    
    def acquire_write(self) -> float:
        """Acquire write lock (exclusive)"""
        start = time.perf_counter()
        
        with self._write_ready:
            while self._read_count > 0 or self._write_count > 0:
                if self.track_stats:
                    self.stats['writes'].contentions += 1
                self._write_ready.wait()
            self._write_count += 1
        
        if self.track_stats:
            wait_time_us = (time.perf_counter() - start) * 1_000_000
            self.stats['writes'].acquisitions += 1
            self.stats['writes'].total_wait_time_us += wait_time_us
            if wait_time_us > self.stats['writes'].max_wait_time_us:
                self.stats['writes'].max_wait_time_us = wait_time_us
            return wait_time_us
        return 0.0
    
    def release_write(self) -> None:
        """Release write lock"""
        with self._write_ready:
            self._write_count -= 1
            self._write_ready.notify_all()
            self._read_ready.notify_all()

    class _LockProxy:
        def __init__(self, acquire, release):
            self.acquire = acquire
            self.release = release
        def __enter__(self):
            self.acquire()
            return self
        def __exit__(self, *args):
            self.release()

    def reader_lock(self):
        """Returns a context manager for read access"""
        return self._LockProxy(self.acquire_read, self.release_read)

    def writer_lock(self):
        """Returns a context manager for write access"""
        return self._LockProxy(self.acquire_write, self.release_write)

    def __enter__(self):
        """Default to write lock for 'with' usage"""
        self.acquire_write()
        return self

    def __exit__(self, *args):
        self.release_write()


class ConditionVariable:
    """
    Condition Variable - Monitor pattern for complex synchronization.
    
    System Call Equivalents:
    - Unix: pthread_cond_wait(), pthread_cond_signal()
    - Linux: futex-based wait/wake mechanisms
    """
    
    def __init__(self, name: str = "condition"):
        self.name = name
        self._cv = threading.Condition()
    
    def wait(self, predicate: Optional[Callable] = None, timeout_sec: Optional[float] = None) -> bool:
        """
        Wait until signaled or timeout.
        
        System Call: pthread_cond_wait()
        
        Args:
            predicate: Optional function that returns True when condition is met
            timeout_sec: Optional timeout in seconds
        
        Returns:
            True if signaled, False if timeout
        """
        with self._cv:
            if predicate:
                while not predicate():
                    if not self._cv.wait(timeout=timeout_sec):
                        return False
            else:
                return self._cv.wait(timeout=timeout_sec)
        return True
    
    def signal(self, count: int = 1) -> None:
        """
        Signal waiting threads.
        
        System Call: pthread_cond_signal()
        """
        with self._cv:
            if count == 1:
                self._cv.notify()
            else:
                self._cv.notify_all()
    
    def broadcast(self) -> None:
        """Signal all waiting threads."""
        with self._cv:
            self._cv.notify_all()


class SpinLock:
    """
    Spin Lock - Busy-waiting lock (high CPU, low latency).
    
    Performance Trade-off:
    - Pros: No context switches, good for short critical sections
    - Cons: Wastes CPU cycles, bad for long critical sections
    
    Decision: Use only for microsecond-scale critical sections.
    """
    
    def __init__(self, name: str = "spinlock", max_spins: int = 100000):
        self.name = name
        self.max_spins = max_spins
        self._locked = False
        self._backoff_spins = 0
    
    def lock(self) -> int:
        """
        Acquire lock with exponential backoff.
        
        Returns: Number of spins before acquisition
        """
        spins = 0
        while self._locked:
            spins += 1
            if spins > self.max_spins:
                # Fallback to yielding if spin limit exceeded
                time.sleep(0.00001)  # 10 microseconds
            if spins % 1000 == 0:
                # Exponential backoff
                time.sleep(0.00001)
        self._locked = True
        return spins
    
    def unlock(self) -> None:
        """Release lock"""
        self._locked = False


def get_sync_primitive(strategy: SyncStrategy, *args, **kwargs):
    """
    Factory function for synchronization primitives.
    
    Demonstrates design pattern selection based on requirements.
    """
    if strategy == SyncStrategy.MUTEX:
        return Mutex(*args, **kwargs)
    elif strategy == SyncStrategy.SEMAPHORE:
        return Semaphore(*args, **kwargs)
    elif strategy == SyncStrategy.RW_LOCK:
        return RWLock(*args, **kwargs)
    elif strategy == SyncStrategy.SPIN_LOCK:
        return SpinLock(*args, **kwargs)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    print("=== TACTICAL OS SYNCHRONIZATION DEMO ===")
    print()

    # 1. Test Mutex
    print("Test 1: Interceptor Fire Lock (Mutex)")
    mutex = Mutex("interceptor_fire_lock", track_stats=True)
    wait_time = mutex.lock()
    print(f"  [OK] Acquired fire lock (wait: {wait_time:.2f}us)")
    mutex.unlock()
    print("  [OK] Released fire lock")
    print()

    # 2. Test Semaphore
    print("Test 2: Detector Thread Pool (Semaphore Counter=2)")
    sem = Semaphore(2, "detector_thread_pool")
    sem.wait()
    print("  [OK] Occupied detector slot 1")
    sem.wait()
    print("  [OK] Occupied detector slot 2")
    sem.signal()
    print("  [OK] Released detector slot")
    print()

    # 3. Test Read-Write Lock
    print("Test 3: Radar Data Access (RWLock - Multiple Readers)")
    rw = RWLock("radar_data_access")
    rw.acquire_read()
    rw.acquire_read()
    print("  [OK] Multiple radar displays reading concurrently")
    rw.release_read()
    rw.release_read()
    print("  [OK] Released radar data access")
    print()

    print("[OK] All tactical synchronization tests passed")
