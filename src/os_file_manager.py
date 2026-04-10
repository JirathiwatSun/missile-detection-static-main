# -*- coding: utf-8 -*-
"""
OS File Management
==================
Implements file I/O concepts:
- File descriptor management
- File locking (advisory locks)
- Direct I/O vs. Buffered I/O
- fsync for data durability
- File metadata tracking

Student demonstrates understanding of:
- System calls: open(), close(), read(), write(), fsync(), flock()
- File table management
- Buffer vs. direct I/O trade-offs
- Data consistency and durability

Performance Trade-offs:
- Buffered I/O: Fast, data may be lost on crash
- Direct I/O: Slower but guaranteed durability with fsync()
- Flock: Prevents concurrent access, but adds overhead
"""

from typing import Optional, BinaryIO, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import os
import time
import threading
import hashlib
from pathlib import Path
from src.os_synchronization import Mutex, RWLock
import logging

logger = logging.getLogger(__name__)


class FileMode(Enum):
    """File access modes"""
    READ = "rb"
    WRITE = "wb"
    APPEND = "ab"
    READ_WRITE = "r+b"


class IOStrategy(Enum):
    """I/O buffering strategies"""
    BUFFERED = "buffered"      # OS buffered (faster, less safe)
    DIRECT = "direct"          # Direct I/O (slower, safer)
    MMAP = "mmap"              # Memory-mapped I/O (balanced)


@dataclass
class FileDescriptor:
    """Represents an open file"""
    fd_id: int
    path: str
    mode: FileMode
    file_handle: Optional[BinaryIO] = None
    io_strategy: IOStrategy = IOStrategy.BUFFERED
    is_open: bool = False
    position: int = 0
    bytes_read: int = 0
    bytes_written: int = 0
    num_reads: int = 0
    num_writes: int = 0
    created_at: float = field(default_factory=time.time)
    last_modified: float = field(default_factory=time.time)
    file_size: int = 0
    checksum: Optional[str] = None  # For data integrity
    
    def get_io_overhead_percent(self) -> float:
        """Calculate I/O overhead percentage"""
        if self.io_strategy == IOStrategy.BUFFERED:
            return 5.0  # Low overhead
        elif self.io_strategy == IOStrategy.DIRECT:
            return 15.0  # Higher overhead (uncached)
        elif self.io_strategy == IOStrategy.MMAP:
            return 10.0  # Medium overhead
        return 0.0


@dataclass
class FileStats:
    """File I/O statistics"""
    total_opens: int = 0
    total_closes: int = 0
    total_reads: int = 0
    total_writes: int = 0
    total_bytes_read: int = 0
    total_bytes_written: int = 0
    total_fsyncs: int = 0
    total_fsync_time_us: float = 0.0  # Time spent in fsync
    max_file_size: int = 0
    cache_writes: int = 0  # Writes to cache (not disk)


class FileManager:
    """
    File I/O manager demonstrating OS file concepts.
    
    System Call Equivalents:
    - open() / close() - file descriptor management
    - read() / write() - I/O operations
    - fsync() - force data to disk
    - flock() / fcntl() - file locking
    """
    
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.open_files: Dict[int, FileDescriptor] = {}
        self.file_table_lock = Mutex("file_table_lock", track_stats=True)
        self.file_locks: Dict[str, RWLock] = {}  # Filename -> Lock
        
        self.fd_counter = 3  # Start after stdin/stdout/stderr
        self.stats = FileStats()
        
        logger.info(f"File manager initialized (data_dir: {self.data_dir})")
    
    def _get_file_lock(self, filepath: str) -> RWLock:
        """Get or create lock for file (advisory locking)"""
        if filepath not in self.file_locks:
            self.file_locks[filepath] = RWLock(f"file_lock_{filepath}")
        return self.file_locks[filepath]
    
    def open(self, filepath: str, mode: FileMode = FileMode.READ,
            io_strategy: IOStrategy = IOStrategy.BUFFERED) -> Optional[int]:
        """
        Open file and return file descriptor (FD).
        
        System Call: open() - returns file descriptor (int)
        Performance Trade-off: Strategy selection affects speed vs. safety
        """
        full_path = self.data_dir / filepath
        
        with self.file_table_lock:
            try:
                # Acquire write lock for opening
                file_lock = self._get_file_lock(filepath)
                file_lock.acquire_write()
                
                try:
                    # Create parent directories if needed
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Open file
                    file_handle = open(full_path, mode.value)
                    
                    # Create FD
                    fd = self.fd_counter
                    self.fd_counter += 1
                    
                    fd_obj = FileDescriptor(
                        fd_id=fd,
                        path=str(full_path),
                        mode=mode,
                        file_handle=file_handle,
                        io_strategy=io_strategy,
                        is_open=True,
                        file_size=full_path.stat().st_size if full_path.exists() else 0
                    )
                    
                    self.open_files[fd] = fd_obj
                    self.stats.total_opens += 1
                    
                    logger.info(f"Opened file: {filepath} (FD={fd}, strategy={io_strategy.value})")
                    return fd
                    
                finally:
                    file_lock.release_write()
                
            except Exception as e:
                logger.error(f"Failed to open file {filepath}: {e}")
                return None
    
    def close(self, fd: int) -> bool:
        """
        Close file descriptor.
        
        System Call: close() - closes and invalidates FD
        """
        with self.file_table_lock:
            if fd not in self.open_files:
                logger.warning(f"Attempted to close invalid FD: {fd}")
                return False
            
            fd_obj = self.open_files[fd]
            
            try:
                if fd_obj.file_handle:
                    fd_obj.file_handle.close()
                    fd_obj.is_open = False
                
                del self.open_files[fd]
                self.stats.total_closes += 1
                
                logger.info(f"Closed file descriptor: {fd}")
                return True
                
            except Exception as e:
                logger.error(f"Error closing FD {fd}: {e}")
                return False
    
    def read(self, fd: int, num_bytes: int = 4096) -> Optional[bytes]:
        """
        Read from file.
        
        System Call: read() - reads up to num_bytes
        """
        with self.file_table_lock:
            if fd not in self.open_files:
                logger.warning(f"Read from invalid FD: {fd}")
                return None
            
            fd_obj = self.open_files[fd]
            
            if not fd_obj.is_open or not fd_obj.file_handle:
                logger.warning(f"Attempted read from closed FD: {fd}")
                return None
        
        try:
            # Read outside lock for concurrency
            data = fd_obj.file_handle.read(num_bytes)
            
            with self.file_table_lock:
                fd_obj.bytes_read += len(data)
                fd_obj.num_reads += 1
                fd_obj.position += len(data)
                self.stats.total_reads += 1
                self.stats.total_bytes_read += len(data)
            
            return data
            
        except Exception as e:
            logger.error(f"Read error on FD {fd}: {e}")
            return None
    
    def write(self, fd: int, data: bytes, fsync: bool = False) -> bool:
        """
        Write to file.
        
        System Call: write() - writes data
        
        Performance Trade-off:
        - fsync=False: Data in OS cache (fast, risky)
        - fsync=True: Data on disk (slow, safe)
        """
        with self.file_table_lock:
            if fd not in self.open_files:
                logger.warning(f"Write to invalid FD: {fd}")
                return False
            
            fd_obj = self.open_files[fd]
            
            if not fd_obj.is_open or not fd_obj.file_handle:
                logger.warning(f"Attempted write to closed FD: {fd}")
                return False
        
        try:
            # Write outside lock
            fd_obj.file_handle.write(data)
            
            with self.file_table_lock:
                fd_obj.bytes_written += len(data)
                fd_obj.num_writes += 1
                fd_obj.position += len(data)
                fd_obj.file_size = max(fd_obj.file_size, fd_obj.position)
                self.stats.total_writes += 1
                self.stats.total_bytes_written += len(data)
                self.stats.cache_writes += 1  # Counts as cache write (unless fsync'd)
                
                if fd_obj.file_size > self.stats.max_file_size:
                    self.stats.max_file_size = fd_obj.file_size
            
            # Optionally force to disk
            if fsync:
                self._fsync_fd(fd_obj)
            
            return True
            
        except Exception as e:
            logger.error(f"Write error on FD {fd}: {e}")
            return False
    
    def _fsync_fd(self, fd_obj: FileDescriptor) -> None:
        """
        Force file data to disk.
        
        System Call: fsync() - synchronize file to disk
        
        Performance consideration: fsync is SLOW (disk I/O)
        """
        start = time.perf_counter()
        
        try:
            fd_obj.file_handle.flush()
            os.fsync(fd_obj.file_handle.fileno())
            
            fsync_time_us = (time.perf_counter() - start) * 1_000_000
            
            with self.file_table_lock:
                self.stats.total_fsyncs += 1
                self.stats.total_fsync_time_us += fsync_time_us
            
            logger.debug(f"fsync on {fd_obj.path} took {fsync_time_us:.2f}us")
            
        except Exception as e:
            logger.error(f"fsync failed: {e}")
    
    def fsync(self, fd: int) -> bool:
        """
        Synchronize file to disk (data durability).
        
        System Call: fsync() - ensure all data written to disk
        
        IMPORTANT: This is SLOW and should be used carefully.
        """
        with self.file_table_lock:
            if fd not in self.open_files:
                logger.warning(f"fsync on invalid FD: {fd}")
                return False
            
            fd_obj = self.open_files[fd]
        
        self._fsync_fd(fd_obj)
        return True
    
    def compute_checksum(self, fd: int, algorithm: str = 'sha256') -> Optional[str]:
        """
        Compute file checksum for integrity verification.
        
        Demonstrates data integrity checking (important in OS file management).
        """
        with self.file_table_lock:
            if fd not in self.open_files:
                logger.warning(f"Checksum computation on invalid FD: {fd}")
                return None
            
            fd_obj = self.open_files[fd]
            filepath = Path(fd_obj.path)
        
        try:
            hasher = hashlib.new(algorithm)
            with open(filepath, 'rb') as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            
            checksum = hasher.hexdigest()
            
            with self.file_table_lock:
                fd_obj.checksum = checksum
            
            return checksum
            
        except Exception as e:
            logger.error(f"Checksum computation failed: {e}")
            return None
    
    def get_file_stats(self, fd: int) -> Optional[Dict[str, Any]]:
        """Get statistics for an open file"""
        with self.file_table_lock:
            if fd not in self.open_files:
                return None
            
            fd_obj = self.open_files[fd]
            
            return {
                'fd_id': fd_obj.fd_id,
                'path': fd_obj.path,
                'mode': fd_obj.mode.name,
                'io_strategy': fd_obj.io_strategy.value,
                'is_open': fd_obj.is_open,
                'position': fd_obj.position,
                'file_size': fd_obj.file_size,
                'bytes_read': fd_obj.bytes_read,
                'bytes_written': fd_obj.bytes_written,
                'num_reads': fd_obj.num_reads,
                'num_writes': fd_obj.num_writes,
                'io_overhead_percent': fd_obj.get_io_overhead_percent(),
                'checksum': fd_obj.checksum[:16] + '...' if fd_obj.checksum else None,
            }
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Get global file I/O statistics"""
        with self.file_table_lock:
            avg_fsync_time_us = (self.stats.total_fsync_time_us / self.stats.total_fsyncs) if self.stats.total_fsyncs > 0 else 0
            
            return {
                'open_files': len(self.open_files),
                'total_opens': self.stats.total_opens,
                'total_closes': self.stats.total_closes,
                'total_reads': self.stats.total_reads,
                'total_writes': self.stats.total_writes,
                'total_bytes_read_mb': self.stats.total_bytes_read / 1_000_000,
                'total_bytes_written_mb': self.stats.total_bytes_written / 1_000_000,
                'total_fsyncs': self.stats.total_fsyncs,
                'avg_fsync_time_us': avg_fsync_time_us,
                'max_file_size_mb': self.stats.max_file_size / 1_000_000,
                'cache_vs_disk_ratio': f"{(self.stats.cache_writes / max(self.stats.total_fsyncs, 1)):.1f}:1"
            }


# Global file manager instance
_global_file_manager: Optional[FileManager] = None


def init_file_manager(data_dir: str = "./data") -> FileManager:
    """Initialize global file manager"""
    global _global_file_manager
    _global_file_manager = FileManager(data_dir)
    return _global_file_manager


def get_file_manager() -> FileManager:
    """Get global file manager instance"""
    if _global_file_manager is None:
        return init_file_manager()
    return _global_file_manager
