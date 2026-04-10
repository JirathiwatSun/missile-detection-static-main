# Complete User Manual - OS Components Testing & Usage

## Table of Contents

1. [Prerequisites & Setup](#prerequisites--setup)
2. [Quick Start](#quick-start)
3. [Testing Individual Components](#testing-individual-components)
4. [Running the Integrated Demo](#running-the-integrated-demo)
5. [Advanced Usage](#advanced-usage)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites & Setup

### Step 1: Verify Python Version

```bash
python --version
```

**Expected Output:**
```
Python 3.8 or higher (3.10+ recommended)
```

**If not installed:**
- Download from https://www.python.org/downloads/
- Or use package manager: `brew install python3` (Mac) / `apt install python3` (Linux)

---

### Step 2: Navigate to Project Directory

**Windows:**
```bash
cd C:\Users\YourUsername\Downloads\missile-detection-static-main
```

**macOS/Linux:**
```bash
cd ~/Downloads/missile-detection-static-main
```

**Verify you're in the right place:**
```bash
ls
```

**Expected Output:**
```
src/
docs/
data/
demo_os_features.py
02_COMPONENTS_TECHNICAL_DEEP_DIVE.md
IMPLEMENTATION_SUMMARY.md
requirements.txt
README.md
...
```

---

### Step 3: Check Python Path

```bash
python -c "import sys; print('Python executable:', sys.executable)"
```

**Expected Output:**
```
Python executable: /path/to/python/executable
```

---

## Quick Start

### Option 1: Run Everything (Fastest)

```bash
python demo_os_features.py
```

**Expected Output:** ~5 minutes of demonstrations with statistics

**What it tests:**
- [OK] All synchronization primitives
- [OK] Memory management
- [OK] Task scheduling
- [OK] File I/O
- [OK] Integrated system

---

### Option 2: Test Individual Components (Recommended for Learning)

Follow sections below for step-by-step testing

---

## Testing Individual Components

### 1. Testing Synchronization Primitives

#### 1.1 Test Mutex (Binary Semaphore)

**Command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_synchronization import Mutex
import time

print('=== MUTEX TEST ===')
print()

# Create mutex with statistics tracking
mutex = Mutex('interceptor_fire_lock', track_stats=True)
print('[OK] Created Tactical Mutex')
print()

# Test basic lock/unlock
print('Test 1: Missile Guidance Lock')
print('-' * 50)

for i in range(5):
    mutex.lock()
    print(f'  Iteration {i+1}: GUIDANCE SECURED')
    time.sleep(0.01)
    mutex.unlock()
    print(f'  Iteration {i+1}: GUIDANCE RELEASED')

print()

# Show statistics
print('Test 2: Synchronization Telemetry')
print('-' * 50)
stats = mutex.stats
print(f'  Total acquisitions: {stats.acquisitions}')
print(f'  Contentions (waits): {stats.contentions}')
print(f'  Max wait time: {stats.max_wait_time_us:.2f}us')
print(f'  Avg wait time: {stats.avg_wait_time_us():.2f}us')
print()
print('[OK] Tactical Mutex test passed')
"
```

**Expected Output:**
```
=== MUTEX TEST ===

[OK] Created Mutex

Test 1: Basic lock/unlock
--------------------------------------------------
  Iteration 1: Locked
  Iteration 1: Unlocked
  Iteration 2: Locked
  Iteration 2: Unlocked
  ...
  Iteration 5: Unlocked

Test 2: Statistics
--------------------------------------------------
  Total acquisitions: 5
  Contentions (waits): 0
  Max wait time: 0.00us
  Avg wait time: 0.00us

[OK] Mutex test passed
```

---

#### 1.2 Test Semaphore (Counting)

**Command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_synchronization import Semaphore

print('=== SEMAPHORE TEST ===')
print()

# Create semaphore (max 3 resources)
sem = Semaphore(3, 'radar_processing_threads', track_stats=True)
print('[OK] Created Tactical Semaphore (Pool size: 3)')
print()

# Simulate resource allocation
print('Test 1: Radar Thread Allocation')
print('-' * 50)

print(f'  Initial capacity: {sem.count}')
print()

# Allocate resources
for i in range(3):
    sem.wait()
    print(f'  After assignment {i+1}: slots_remaining = {sem.count}')

print()
print('  All detector modules active!')
print()

# Deallocate resources
print('Test 2: Module Deactivation')
print('-' * 50)

for i in range(3):
    sem.signal()
    print(f'  After release {i+1}: slots_available = {sem.count}')

print()
print('[OK] Tactical Semaphore test passed')
"
```

**Expected Output:**
```
=== SEMAPHORE TEST ===

[OK] Created Semaphore with initial count: 3

Test 1: Resource allocation
--------------------------------------------------
  Initial count: 3

  After wait 1: count = 2
  After wait 2: count = 1
  After wait 3: count = 0

  All resources allocated!

Test 2: Resource deallocation
--------------------------------------------------
  After signal 1: count = 1
  After signal 2: count = 2
  After signal 3: count = 3

[OK] Semaphore test passed
```

---

#### 1.3 Test RWLock (Read-Write Lock)

**Command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_synchronization import RWLock

print('=== RWLOCK TEST (Multi-Reader) ===')
print()

rwlock = RWLock('radar_data_access', track_stats=True)
print('[OK] Created RWLock')
print()

# Test multiple readers
print('Test 1: Multiple readers (concurrent)')
print('-' * 50)

for i in range(5):
    rwlock.acquire_read()
    print(f'  Reader {i+1} acquired read lock')

print()
print(f'  Current read holders: 5')
print(f'  [OK] Multiple readers can hold lock simultaneously')
print()

# Release readers
for i in range(5):
    rwlock.release_read()
    print(f'  Reader {i+1} released read lock')

print()

# Test exclusive writer
print('Test 2: Exclusive writer')
print('-' * 50)

rwlock.acquire_write()
print(f'  Writer acquired EXCLUSIVE write lock')

print(f'  [OK] Writer has exclusive access')
print()

rwlock.release_write()
print(f'  Writer released write lock')

print()

# Show statistics
print('Test 3: Statistics')
print('-' * 50)

read_stats = rwlock.stats['reads']
write_stats = rwlock.stats['writes']

print(f'  Read operations:')
print(f'    - Acquisitions: {read_stats.acquisitions}')
print(f'    - Contentions: {read_stats.contentions}')
print()
print(f'  Write operations:')
print(f'    - Acquisitions: {write_stats.acquisitions}')
print(f'    - Contentions: {write_stats.contentions}')

print()
print('[OK] RWLock test passed')
"
```

**Expected Output:**
```
=== RWLOCK TEST (Multi-Reader) ===

[OK] Created RWLock

Test 1: Multiple readers (concurrent)
--------------------------------------------------
  Reader 1 acquired read lock
  Reader 2 acquired read lock
  Reader 3 acquired read lock
  Reader 4 acquired read lock
  Reader 5 acquired read lock

  Current read holders: 5
  [OK] Multiple readers can hold lock simultaneously

  Reader 1 released read lock
  Reader 2 released read lock
  Reader 3 released read lock
  Reader 4 released read lock
  Reader 5 released read lock

Test 2: Exclusive writer
--------------------------------------------------
  Writer acquired EXCLUSIVE write lock
  [OK] Writer has exclusive access

  Writer released write lock

Test 3: Statistics
--------------------------------------------------
  Read operations:
    - Acquisitions: 5
    - Contentions: 0

  Write operations:
    - Acquisitions: 1
    - Contentions: 0

[OK] RWLock test passed
```

---

#### 1.4 Test Condition Variable

**Command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_synchronization import ConditionVariable

print('=== CONDITION VARIABLE TEST ===')
print()

cv = ConditionVariable('interceptor_ready_signal')
print('[OK] Created ConditionVariable')
print()

# Test signal/wait pattern
print('Test 1: Signal and wait pattern')
print('-' * 50)

shared_state = {'ready': False}

print('  Scenario: Producer signals when data is ready')
print()

# Simulate producer
print('  Producer: Setting state to ready...')
shared_state['ready'] = True
cv.signal()
print('  Producer: Signaled waiting threads')
print()

# Simulate consumer
print('  Consumer: Waiting for ready state...')
is_ready = cv.wait(
    predicate=lambda: shared_state['ready'],
    timeout_sec=1.0
)
print(f'  Consumer: Woken up! Ready state: {is_ready}')

print()
print('[OK] Condition Variable test passed')
"
```

**Expected Output:**
```
=== CONDITION VARIABLE TEST ===

[OK] Created ConditionVariable

Test 1: Signal and wait pattern
--------------------------------------------------
  Scenario: Producer signals when data is ready

  Producer: Setting state to ready...
  Producer: Signaled waiting threads

  Consumer: Waiting for ready state...
  Consumer: Woken up! Ready state: True

[OK] Condition Variable test passed
```

---

### 2. Testing Memory Management

#### 2.1 Test Memory Manager

**Command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_memory import MemoryManager, AllocationStrategy

print('=== MEMORY MANAGER TEST ===')
print()

# Create memory manager
mem_mgr = MemoryManager(
    max_size_bytes=100_000_000,
    strategy=AllocationStrategy.POOL
)
print('[OK] Created Tactical MemoryManager (100MB Capacity)')
print()

# Test allocation
print('Test 1: Missile Telemetry Allocation')
print('-' * 50)

blocks = []
for i in range(5):
    block = mem_mgr.allocate(1_000_000, owner=f'missile_data_{i}')
    blocks.append(block)
    print(f'  Allocated block {i}: {block.address_str()} (1MB TELEMETRY)')

print()

# Show statistics
stats = mem_mgr.get_stats()
print('Test 2: Memory statistics')
print('-' * 50)
print(f'  Current allocation: {stats.current_in_use / 1_000_000:.1f}MB')
print(f'  Peak allocation: {stats.peak_in_use / 1_000_000:.1f}MB')
print(f'  Total allocations: {stats.num_allocations}')
print(f'  Fragmentation ratio: {stats.fragmentation_ratio:.2%}')
print()

# Test deallocation
print('Test 3: Memory deallocation')
print('-' * 50)

for i in range(2):
    mem_mgr.free(blocks[i])
    print(f'  Freed block {i}')

print()

stats = mem_mgr.get_stats()
print('Test 4: After deallocation')
print('-' * 50)
print(f'  Current allocation: {stats.current_in_use / 1_000_000:.1f}MB')
print(f'  Free blocks: {len(mem_mgr.free_blocks)}')
print(f'  Total frees: {stats.num_frees}')
print()

print('[OK] Memory Manager test passed')
"
```

**Expected Output:**
```
=== MEMORY MANAGER TEST ===

[OK] Created MemoryManager (100MB capacity)

Test 1: Memory allocation
--------------------------------------------------
  Allocated block 0: 0x0000000000001000 (1MB)
  Allocated block 1: 0x0000000000001001 (1MB)
  Allocated block 2: 0x0000000000001002 (1MB)
  Allocated block 3: 0x0000000000001003 (1MB)
  Allocated block 4: 0x0000000000001004 (1MB)

Test 2: Memory statistics
--------------------------------------------------
  Current allocation: 5.0MB
  Peak allocation: 5.0MB
  Total allocations: 5
  Fragmentation ratio: 0.00%

Test 3: Memory deallocation
--------------------------------------------------
  Freed block 0
  Freed block 1

Test 4: After deallocation
--------------------------------------------------
  Current allocation: 3.0MB
  Free blocks: 2
  Total frees: 2

[OK] Memory Manager test passed
```

---

#### 2.2 Test Frame Buffer Pool

**Command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_memory import FrameBufferPool
import time

print('=== FRAME BUFFER POOL TEST ===')
print()

# Create pool
pool = FrameBufferPool(
    buffer_size=1920*1080*3*4,
    num_buffers=5,
    height=1080,
    width=1920,
    channels=3
)
capacity_mb = (5 * 1920 * 1080 * 3 * 4) / 1_000_000
print(f'[OK] Created Frame Buffer Pool')
print(f'  Capacity: {capacity_mb:.1f}MB (5 buffers × 1920×1080×RGB)')
print()

# Test acquisition
print('Test 1: Buffer acquisition')
print('-' * 50)

acquired_buffers = []
for i in range(3):
    buf = pool.acquire()
    acquired_buffers.append(buf)
    utilization = pool.get_utilization()
    print(f'  Acquired buffer {i+1}: utilization = {utilization:.1f}%')

print()

# Test statistics
print('Test 2: Pool statistics')
print('-' * 50)

stats = pool.get_stats()
print(f'  Total acquired: {stats[\"allocated\"]}')
print(f'  Currently in use: {stats[\"in_use\"]}')
print(f'  Available: {stats[\"available\"]}')
print(f'  Cache hits: {stats[\"cache_hits\"]}')
print()

# Test release
print('Test 3: Buffer release')
print('-' * 50)

for i, buf in enumerate(acquired_buffers):
    pool.release(buf)
    utilization = pool.get_utilization()
    print(f'  Released buffer {i+1}: utilization = {utilization:.1f}%')

print()

# Performance test
print('Test 4: Performance benchmark')
print('-' * 50)

start = time.perf_counter()
for _ in range(1000):
    buf = pool.acquire()
    pool.release(buf)
elapsed_ms = (time.perf_counter() - start) * 1000

print(f'  1000 acquire/release cycles: {elapsed_ms:.2f}ms')
print(f'  Average time per cycle: {elapsed_ms/1000*1000:.2f}us')
print(f'  [OK] Very fast (expected: <10us)')
print()

print('[OK] Frame Buffer Pool test passed')
"
```

**Expected Output:**
```
=== FRAME BUFFER POOL TEST ===

[OK] Created Frame Buffer Pool
  Capacity: 24.2MB (5 buffers × 1920×1080×RGB)

Test 1: Buffer acquisition
--------------------------------------------------
  Acquired buffer 1: utilization = 20.0%
  Acquired buffer 2: utilization = 40.0%
  Acquired buffer 3: utilization = 60.0%

Test 2: Pool statistics
--------------------------------------------------
  Total acquired: 3
  Currently in use: 3
  Available: 2
  Cache hits: 3

Test 3: Buffer release
--------------------------------------------------
  Released buffer 1: utilization = 40.0%
  Released buffer 2: utilization = 20.0%
  Released buffer 3: utilization = 0.0%

Test 4: Performance benchmark
--------------------------------------------------
  1000 acquire/release cycles: 5.23ms
  Average time per cycle: 5.23us
  [OK] Very fast (expected: <10us)

[OK] Frame Buffer Pool test passed
```

---

### 3. Testing Task Scheduler

#### 3.1 Test Priority Scheduling

**Command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_scheduler import (
    init_global_scheduler, 
    SchedulingStrategy, 
    TaskPriority
)
import time

print('=== TASK SCHEDULER TEST ===')
print()

# Initialize scheduler
scheduler = init_global_scheduler(
    strategy=SchedulingStrategy.PRIORITY,
    max_workers=2
)
scheduler.start()
print('[OK] Started scheduler (Priority strategy, 2 workers)')
print()

# Define tasks
def background_task(task_id):
    time.sleep(0.1)
    return f'Background {task_id} completed'

def normal_task(task_id):
    time.sleep(0.1)
    return f'Normal {task_id} completed'

def high_priority_task(task_id):
    time.sleep(0.05)
    return f'High Priority {task_id} completed'

# Submit tasks with different priorities
print('Test 1: Submit tasks with different priorities')
print('-' * 50)

task_ids = []
tasks = [
    (background_task, (1,), TaskPriority.BACKGROUND, 'background'),
    (normal_task, (1,), TaskPriority.NORMAL, 'normal'),
    (high_priority_task, (1,), TaskPriority.HIGH, 'high-priority'),
    (normal_task, (2,), TaskPriority.NORMAL, 'normal'),
]

for func, args, priority, name in tasks:
    tid = scheduler.submit_task(func, args=args, priority=priority, name=name)
    task_ids.append(tid)
    print(f'  Submitted {name}: task_id={tid}')

print()

# Wait for completion
print('Test 2: Wait for execution')
print('-' * 50)
print('  Processing tasks...')
time.sleep(1)

print()

# Get statistics
print('Test 3: Scheduler statistics')
print('-' * 50)

stats = scheduler.get_global_stats()
print(f'  Total tasks created: {stats[\"total_tasks_created\"]}')
print(f'  Total tasks completed: {stats[\"total_tasks_completed\"]}')
print(f'  Running tasks: {stats[\"running_tasks\"]}')
print(f'  Context switches: {stats[\"context_switches\"]}')
print(f'  Queue depths: {stats[\"queue_depths\"]}')
print(f'  Avg turnaround: {stats[\"avg_turnaround_time_ms\"]:.2f}ms')

print()

scheduler.stop()
print('[OK] Task Scheduler test passed')
"
```

**Expected Output:**
```
=== TASK SCHEDULER TEST ===

[OK] Started scheduler (Priority strategy, 2 workers)

Test 1: Submit tasks with different priorities
--------------------------------------------------
  Submitted background: task_id=0
  Submitted normal: task_id=1
  Submitted high-priority: task_id=2
  Submitted normal: task_id=3

Test 2: Wait for execution
--------------------------------------------------
  Processing tasks...

Test 3: Scheduler statistics
--------------------------------------------------
  Total tasks created: 4
  Total tasks completed: 4
  Running tasks: 0
  Context switches: 8
  Queue depths: {'BACKGROUND': 0, 'LOW': 0, 'NORMAL': 0, 'HIGH': 0, 'REALTIME': 0}
  Avg turnaround: 250.50ms

[OK] Task Scheduler test passed
```

---

### 4. Testing File Management

#### 4.1 Test File I/O Operations

**Command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_file_manager import FileManager, FileMode, IOStrategy

print('=== FILE MANAGER TEST ===')
print()

# Create file manager
fm = FileManager(data_dir='./test_os_files')
print('[OK] Created FileManager (data directory: ./test_os_files)')
print()

# Test buffered write
print('Test 1: Buffered I/O (Fast)')
print('-' * 50)

fd_buf = fm.open('buffered.log', 
                 mode=FileMode.WRITE,
                 io_strategy=IOStrategy.BUFFERED)
print(f'  Opened buffered file: FD={fd_buf}')

data = b'Detection log entry: missile detected at (100, 200)\\n' * 10
fm.write(fd_buf, data, fsync=False)
print(f'  Written {len(data)} bytes (buffered, no fsync)')

fm.close(fd_buf)
print(f'  Closed file')
print()

# Test direct write with fsync
print('Test 2: Direct I/O + fsync (Safe)')
print('-' * 50)

fd_direct = fm.open('critical.log',
                    mode=FileMode.WRITE,
                    io_strategy=IOStrategy.DIRECT)
print(f'  Opened direct I/O file: FD={fd_direct}')

critical_data = b'CRITICAL: Multiple threats detected!\\n'
fm.write(fd_direct, critical_data, fsync=True)
print(f'  Written {len(critical_data)} bytes (with fsync)')

fm.close(fd_direct)
print(f'  Closed file')
print()

# Show statistics
print('Test 3: File I/O statistics')
print('-' * 50)

stats = fm.get_global_stats()
print(f'  Total opens: {stats[\"total_opens\"]}')
print(f'  Total closes: {stats[\"total_closes\"]}')
print(f'  Total bytes written: {stats[\"total_bytes_written_mb\"]:.2f}MB')
print(f'  Total fsyncs: {stats[\"total_fsyncs\"]}')
print(f'  Avg fsync time: {stats[\"avg_fsync_time_us\"]:.2f}us')
print()

print('[OK] File Manager test passed')
"
```

**Expected Output:**
```
=== FILE MANAGER TEST ===

[OK] Created FileManager (data directory: ./test_os_files)

Test 1: Buffered I/O (Fast)
--------------------------------------------------
  Opened buffered file: FD=3
  Written 500 bytes (buffered, no fsync)
  Closed file

Test 2: Direct I/O + fsync (Safe)
--------------------------------------------------
  Opened direct I/O file: FD=4
  Written 38 bytes (with fsync)
  Closed file

Test 3: File I/O statistics
--------------------------------------------------
  Total opens: 2
  Total closes: 2
  Total bytes written: 0.00MB
  Total fsyncs: 1
  Avg fsync time: 5000.50us

[OK] File Manager test passed
```

---

## Running the Integrated Demo

### Full System Demo

Run the complete demonstration with all components integrated:

**Command:**
```bash
python demo_os_features.py
```

**What it does:**
1. Tests all synchronization primitives
2. Demonstrates memory management
3. Shows task scheduling
4. Tests file I/O
5. Runs integrated system example
6. Prints final statistics

**Expected Runtime:** 3-5 minutes

**Expected Output:** ~500 lines showing all component tests and statistics

### View Demo Output (Save to File)

**Command:**
```bash
python demo_os_features.py > demo_output.txt 2>&1
```

Then view the file:
```bash
cat demo_output.txt
```

---

## Advanced Usage

### 1. Custom Test: Synchronization Under Contention

**Create file: `test_contention.py`**

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test synchronization under contention.
Demonstrates lock performance with competing threads.
"""

import sys
sys.path.insert(0, 'src')

from os_synchronization import Mutex, RWLock
import threading
import time

def test_guidance_lock_contention():
    """Test mutex with multiple threads"""
    print("=== Mutex Contention Test ===")
    
    mutex = Mutex("tactical_frame_buffer", track_stats=True)
    shared_counter = {'value': 0}
    
    def increment():
        for _ in range(100):
            mutex.lock()
            shared_counter['value'] += 1
            mutex.unlock()
    
    threads = [threading.Thread(target=increment) for _ in range(5)]
    
    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start
    
    print(f"  Threads: 5")
    print(f"  Increments per thread: 100")
    print(f"  Final value: {shared_counter['value']}")
    print(f"  Expected: 500")
    print(f"  Time: {elapsed:.3f}s")
    print(f"  Lock stats: {mutex.stats.acquisitions} acquisitions, "
          f"{mutex.stats.contentions} contentions")
    print()

def test_radar_access_contention():
    """Test RWLock with multiple readers and writers"""
    print("=== RWLock Contention Test ===")
    
    rwlock = RWLock("radar_contention_test", track_stats=True)
    shared_data = {'value': 0}
    
    def reader():
        for _ in range(50):
            rwlock.acquire_read()
            _ = shared_data['value']
            rwlock.release_read()
    
    def writer():
        for _ in range(10):
            rwlock.acquire_write()
            shared_data['value'] += 1
            rwlock.release_write()
    
    reader_threads = [threading.Thread(target=reader) for _ in range(10)]
    writer_threads = [threading.Thread(target=writer) for _ in range(2)]
    
    all_threads = reader_threads + writer_threads
    
    start = time.time()
    for t in all_threads:
        t.start()
    for t in all_threads:
        t.join()
    elapsed = time.time() - start
    
    read_stats = rwlock.stats['reads']
    write_stats = rwlock.stats['writes']
    
    print(f"  Reader threads: 10")
    print(f"  Writer threads: 2")
    print(f"  Time: {elapsed:.3f}s")
    print(f"  Read acquisitions: {read_stats.acquisitions}")
    print(f"  Write acquisitions: {write_stats.acquisitions}")
    print(f"  Final value: {shared_data['value']}")
    print()

if __name__ == "__main__":
    test_guidance_lock_contention()
    test_radar_access_contention()
    print("[OK] Contention tests complete")
```

**Run:**
```bash
python test_contention.py
```

---

### 2. Custom Test: Memory Fragmentation

**Create file: `test_fragmentation.py`**

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test memory fragmentation and defragmentation.
"""

import sys
sys.path.insert(0, 'src')

from os_memory import MemoryManager, AllocationStrategy

print("=== Memory Fragmentation Test ===")
print()

mem_mgr = MemoryManager(max_size_bytes=100_000_000, 
                        strategy=AllocationStrategy.BEST_FIT)

print("Allocating 10 blocks...")
blocks = []
for i in range(10):
    block = mem_mgr.allocate(1_000_000, owner=f"block_{i}")
    blocks.append(block)

stats = mem_mgr.get_stats()
print(f"After allocation: fragmentation = {stats.fragmentation_ratio:.2%}")
print()

print("Freeing alternate blocks (creating fragmentation)...")
for i in range(0, 10, 2):
    mem_mgr.free(blocks[i])

stats = mem_mgr.get_stats()
print(f"After deallocation: fragmentation = {stats.fragmentation_ratio:.2%}")
print(f"Defragmentations performed: {stats.num_defragmentations}")
print()

print("Attempting to allocate 6MB block (requires defragmentation)...")
large_block = mem_mgr.allocate(6_000_000, owner="large_block")

if large_block:
    print("[OK] Successfully allocated despite fragmentation")
    stats = mem_mgr.get_stats()
    print(f"After defragmentation: fragmentation = {stats.fragmentation_ratio:.2%}")
else:
    print("[FAIL] Allocation failed")

print()
print("[OK] Fragmentation test complete")
```

**Run:**
```bash
python test_fragmentation.py
```

---

### 3. Integration Example: Using With Missile Tracker

**Create file: `test_integration.py`**

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Example of integrating OS components with missile detection.
"""

import sys
sys.path.insert(0, 'src')

from os_scheduler import init_global_scheduler, TaskPriority
from os_memory import FrameBufferPool, init_memory_manager
from os_file_manager import FileManager, FileMode, IOStrategy
from os_synchronization import RWLock
import time

print("=== OS Components Integration Example ===")
print()

# Initialize all components
print("Initializing OS components...")
scheduler = init_global_scheduler()
scheduler.start()

memory_mgr = init_memory_manager(500_000_000)
frame_pool = FrameBufferPool(
    buffer_size=1920*1080*3*4,
    num_buffers=8,
    height=1080,
    width=1920
)

file_mgr = FileManager("./detection_data")
frame_lock = RWLock("frame_access")

print("[OK] All components initialized")
print()

# Simulate frame processing
print("Simulating detection pipeline...")
print()

def process_and_detect(frame_id):
    """Simulate frame processing"""
    # Get frame buffer
    frame = frame_pool.acquire()
    if frame is None:
        return None
    
    try:
        # Simulate detection (critical section)
        time.sleep(0.01)
        
        # Write detection log
        detection_str = f"Frame {frame_id}: detection complete\n".encode()
        fd = file_mgr.open(f"detections.log", 
                          mode=FileMode.APPEND,
                          io_strategy=IOStrategy.BUFFERED)
        if fd:
            file_mgr.write(fd, detection_str, fsync=False)
            file_mgr.close(fd)
        
        return {"frame": frame_id, "status": "complete"}
    finally:
        frame_pool.release(frame)

# Submit detection tasks
print("Submitting 10 detection tasks to scheduler...")
for i in range(10):
    scheduler.submit_task(
        process_and_detect,
        args=(i,),
        priority=TaskPriority.HIGH,
        name=f"detect_{i}"
    )

print()

# Wait for completion
print("Processing...")
time.sleep(2)

# Print statistics
print()
print("=== Final Statistics ===")
print()

sched_stats = scheduler.get_global_stats()
print("Scheduler:")
print(f"  Tasks completed: {sched_stats['total_tasks_completed']}")
print(f"  Context switches: {sched_stats['context_switches']}")
print()

pool_stats = frame_pool.get_stats()
print("Frame Buffer Pool:")
print(f"  Cache hits: {pool_stats['cache_hits']}")
print(f"  Utilization: {pool_stats['utilization_percent']:.1f}%")
print()

file_stats = file_mgr.get_global_stats()
print("File I/O:")
print(f"  Files written: {file_stats['total_bytes_written_mb']:.4f}MB")
print(f"  Fsyncs: {file_stats['total_fsyncs']}")
print()

scheduler.stop()

print("[OK] Integration test complete")
```

**Run:**
```bash
python test_integration.py
```

---

## Troubleshooting

### Issue 1: "Module not found" Error

**Error:**
```
ModuleNotFoundError: No module named 'os_synchronization'
```

**Solution:**
Make sure you're in the correct directory:
```bash
cd missile-detection-static-main
python -c "import sys; sys.path.insert(0, 'src'); from os_synchronization import Mutex"
```

---

### Issue 2: File Permission Error

**Error:**
```
PermissionError: [Errno 13] Permission denied
```

**Solution:**
Ensure write permissions on the directory:
```bash
# On Linux/Mac
chmod 755 .

# On Windows, right-click folder → Properties → Security → Edit
# Grant full control to your user
```

---

### Issue 3: Out of Memory

**Error:**
```
MemoryError: Unable to allocate ...
```

**Solution:**
Reduce buffer sizes:
```python
pool = FrameBufferPool(
    buffer_size=1280*720*3*4,  # Smaller resolution
    num_buffers=4,  # Fewer buffers
    height=720,
    width=1280,
    channels=3
)
```

---

### Issue 4: Slow Performance

**Symptom:**
Demo runs very slowly (>10 minutes)

**Solution:**
Check system resources:
```bash
# On Mac/Linux
free -h  # Check available memory
top      # Check CPU usage

# On Windows
Get-Process | Where-Object {$_.Memory -gt 100MB}
```

Reduce workload:
```python
# In demo_os_features.py, reduce iteration counts
for i in range(100):  # Instead of 1000
    ...
```

---

## Quick Reference: Common Commands

### Run Full Demo
```bash
python demo_os_features.py
```

### Test Synchronization
```bash
python -c "import sys; sys.path.insert(0, 'src'); from os_synchronization import Mutex; m = Mutex('test'); print('[OK] Mutex works')"
```

### Test Memory
```bash
python -c "import sys; sys.path.insert(0, 'src'); from os_memory import MemoryManager; mm = MemoryManager(); print('[OK] Memory Manager works')"
```

### Test Scheduler
```bash
python -c "import sys; sys.path.insert(0, 'src'); from os_scheduler import TaskScheduler; ts = TaskScheduler(); print('[OK] Scheduler works')"
```

### Test File Manager
```bash
python -c "import sys; sys.path.insert(0, 'src'); from os_file_manager import FileManager; fm = FileManager(); print('[OK] File Manager works')"
```

### Clean Up Test Files
```bash
rm -rf ./test_os_files ./os_demo_data ./detection_data
```

---

## Summary

| Component | Test Command | Expected Time |
|-----------|--------------|----------------|
| Synchronization | `python -c "..."` (individual) | <1s |
| Memory Manager | `python -c "..."` (individual) | <1s |
| Frame Buffer Pool | `python -c "..."` (individual) | <1s |
| Task Scheduler | `python -c "..."` (individual) | 1s |
| File Manager | `python -c "..."` (individual) | <1s |
| Full Demo | `python demo_os_features.py` | 3-5m |

---

## Next Steps

1. ✅ Run the full demo: `python demo_os_features.py`
2. ✅ Test individual components using commands above
3. ✅ Review `docs/03_OS_IMPLEMENTATION_DETAILS.md` for technical details
4. ✅ Check `docs/08_PRESENTATION_CONTENT_GUIDE.md` for presentation tips
5. ✅ Create custom tests for your specific use cases

**Good luck! (START)**
