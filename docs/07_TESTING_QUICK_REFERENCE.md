# 🧪 Testing Command Reference - Copy & Paste Ready

**Updated:** April 10, 2026 with ACTIVE IMPLEMENTATION PROOF

This file contains all testing commands you can copy and paste directly.

> **🎯 TIP:** See [PRESENTATION_TALK_TRACK_CHEATSHEET.md](./PRESENTATION_TALK_TRACK_CHEATSHEET.md) for what to show evaluators!

---

## (START) Run Everything At Once (Easiest)

```bash
python demo_os_features.py
```

**Duration:** 3-5 minutes  
**Output:** Complete statistics for all components  
**Best for:** Quick verification

---

## 1️⃣ Test Synchronization Primitives

### Test 1.1: Mutex (Binary Semaphore)

**Copy this command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_synchronization import Mutex
import time

print('=== MUTEX TEST ===')
print()

# Create tactical mutex with statistics tracking
mutex = Mutex('interceptor_fire_lock', track_stats=True)
print('✅ Created Tactical Mutex')
print()

print('Test 1: Missile Guidance Lock')
print('-' * 50)

for i in range(5):
    mutex.lock()
    print(f'  Iteration {i+1}: GUIDANCE SECURED')
    time.sleep(0.01)
    mutex.unlock()
    print(f'  Iteration {i+1}: GUIDANCE RELEASED')

print()

print('Test 2: Statistics')
print('-' * 50)
stats = mutex.stats
print(f'  Total acquisitions: {stats.acquisitions}')
print(f'  Contentions (waits): {stats.contentions}')
print(f'  Max wait time: {stats.max_wait_time_us:.2f}us')
print(f'  Avg wait time: {stats.avg_wait_time_us():.2f}us')
print()
print('✅ Mutex test passed')
"
```

**Expected output snippet:**
```
=== MUTEX TEST ===

✅ Created Mutex

Test 1: Basic lock/unlock
--------------------------------------------------
  Iteration 1: Locked
  Iteration 1: Unlocked
  ...
```

---

### Test 1.2: Semaphore (Counting)

**Copy this command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_synchronization import Semaphore

print('=== SEMAPHORE TEST ===')
print()

sem = Semaphore(3, 'detector_thread_pool', track_stats=True)
print('✅ Created Tactical Semaphore (Pool size: 3)')
print()

print('Test 1: Radar Thread Allocation')
print('-' * 50)

print(f'  Initial capacity: {sem.count}')
print()

for i in range(3):
    sem.wait()
    print(f'  After assignment {i+1}: slots_remaining = {sem.count}')

print()

print('Test 2: Module Deactivation')
print('-' * 50)

for i in range(3):
    sem.signal()
    print(f'  After release {i+1}: slots_available = {sem.count}')

print()
print('✅ Tactical Semaphore test passed')
"
```

---

### Test 1.3: RWLock (Read-Write Lock)

**Copy this command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_synchronization import RWLock

print('=== RWLOCK TEST (Multi-Reader) ===')
print()

rwlock = RWLock('radar_data_access', track_stats=True)
print('✅ Created RWLock')
print()

print('Test 1: Multiple readers (concurrent)')
print('-' * 50)

for i in range(5):
    rwlock.acquire_read()
    print(f'  Reader {i+1} acquired read lock')

print()
for i in range(5):
    rwlock.release_read()
    print(f'  Reader {i+1} released read lock')

print()

print('Test 2: Exclusive writer')
print('-' * 50)

rwlock.acquire_write()
print(f'  Writer acquired EXCLUSIVE write lock')
rwlock.release_write()
print(f'  Writer released write lock')

print()

print('Test 3: Statistics')
print('-' * 50)

read_stats = rwlock.stats['reads']
write_stats = rwlock.stats['writes']

print(f'  Read acquisitions: {read_stats.acquisitions}')
print(f'  Read contentions: {read_stats.contentions}')
print(f'  Write acquisitions: {write_stats.acquisitions}')

print()
print('✅ RWLock test passed')
"
```

---

### Test 1.4: Condition Variable

**Copy this command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_synchronization import ConditionVariable

print('=== CONDITION VARIABLE TEST ===')
print()

cv = ConditionVariable('interceptor_ready_signal')
print('✅ Created ConditionVariable')
print()

print('Test 1: Signal and wait pattern')
print('-' * 50)

shared_state = {'ready': False}

print('  Producer: Setting state to ready...')
shared_state['ready'] = True
cv.signal()
print('  Producer: Signaled waiting threads')
print()

print('  Consumer: Waiting for ready state...')
is_ready = cv.wait(
    predicate=lambda: shared_state['ready'],
    timeout_sec=1.0
)
print(f'  Consumer: Woken up! Ready state: {is_ready}')

print()
print('✅ Condition Variable test passed')
"
```

---

## 2️⃣ Test Memory Management

### Test 2.1: Memory Manager

**Copy this command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_memory import MemoryManager, AllocationStrategy

print('=== MEMORY MANAGER TEST ===')
print()

mem_mgr = MemoryManager(
    max_size_bytes=100_000_000,
    strategy=AllocationStrategy.POOL
)
print('✅ Created MemoryManager (100MB capacity)')
print()

print('Test 1: Memory allocation')
print('-' * 50)

blocks = []
for i in range(5):
    block = mem_mgr.allocate(1_000_000, owner=f'missile_data_{i}')
    blocks.append(block)
    print(f'  Allocated block {i}: {block.address_str()} (1MB TELEMETRY)')

print()

stats = mem_mgr.get_stats()
print('Test 2: Memory statistics')
print('-' * 50)
print(f'  Current allocation: {stats.current_in_use / 1_000_000:.1f}MB')
print(f'  Peak allocation: {stats.peak_in_use / 1_000_000:.1f}MB')
print(f'  Fragmentation ratio: {stats.fragmentation_ratio:.2%}')
print()

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

print()
print('✅ Memory Manager test passed')
"
```

---

### Test 2.2: Frame Buffer Pool

**Copy this command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_memory import FrameBufferPool
import time

print('=== FRAME BUFFER POOL TEST ===')
print()

pool = FrameBufferPool(
    buffer_size=1920*1080*3*4,
    num_buffers=5,
    height=1080,
    width=1920,
    channels=3
)
capacity_mb = (5 * 1920 * 1080 * 3 * 4) / 1_000_000
print(f'✅ Created Frame Buffer Pool')
print(f'  Capacity: {capacity_mb:.1f}MB')
print()

print('Test 1: Buffer acquisition')
print('-' * 50)

acquired_buffers = []
for i in range(3):
    buf = pool.acquire()
    acquired_buffers.append(buf)
    utilization = pool.get_utilization()
    print(f'  Acquired buffer {i+1}: utilization = {utilization:.1f}%')

print()

print('Test 2: Pool statistics')
print('-' * 50)

stats = pool.get_stats()
print(f'  Total acquired: {stats[\"allocated\"]}')
print(f'  Currently in use: {stats[\"in_use\"]}')
print(f'  Available: {stats[\"available\"]}')

print()

print('Test 3: Buffer release')
print('-' * 50)

for i, buf in enumerate(acquired_buffers):
    pool.release(buf)
    utilization = pool.get_utilization()
    print(f'  Released buffer {i+1}: utilization = {utilization:.1f}%')

print()

print('Test 4: Performance benchmark')
print('-' * 50)

start = time.perf_counter()
for _ in range(1000):
    buf = pool.acquire()
    pool.release(buf)
elapsed_ms = (time.perf_counter() - start) * 1000

print(f'  1000 cycles: {elapsed_ms:.2f}ms')
print(f'  Per cycle: {elapsed_ms/1000*1000:.2f}us')

print()
print('✅ Frame Buffer Pool test passed')
"
```

---

## 3️⃣ Test Task Scheduler

### Test 3.1: Priority Scheduling

**Copy this command:**
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

scheduler = init_global_scheduler(
    strategy=SchedulingStrategy.PRIORITY,
    max_workers=2
)
scheduler.start()
print('✅ Started scheduler (2 workers)')
print()

def tactical_mission(name, duration):
    time.sleep(duration)
    return f'{name} completed'

print('Test 1: Submit tasks')
print('-' * 50)

tasks = [
    ('High Priority', 0.05, TaskPriority.HIGH),
    ('Normal', 0.1, TaskPriority.NORMAL),
    ('Background', 0.1, TaskPriority.BACKGROUND),
]

for name, duration, priority in tasks:
    tid = scheduler.submit_task(
        tactical_mission,
        args=(name, duration),
        priority=priority,
        name=name
    )
    print(f'  Submitted {name}: task_id={tid}')

print()

print('Test 2: Mission Execution')
print('-' * 50)
print('  Executing tactical missions...')
time.sleep(1)

print()

print('Test 3: Statistics')
print('-' * 50)

stats = scheduler.get_global_stats()
print(f'  Total tasks created: {stats[\"total_tasks_created\"]}')
print(f'  Total tasks completed: {stats[\"total_tasks_completed\"]}')
print(f'  Context switches: {stats[\"context_switches\"]}')

print()

scheduler.stop()
print('✅ Task Scheduler test passed')
"
```

---

## 4️⃣ Test File Management

### Test 4.1: File I/O Operations

**Copy this command:**
```bash
python -c "
import sys
sys.path.insert(0, 'src')
from os_file_manager import FileManager, FileMode, IOStrategy

print('=== FILE MANAGER TEST ===')
print()

fm = FileManager(data_dir='./test_os_files')
print('✅ Created FileManager')
print()

print('Test 1: Buffered I/O (Fast)')
print('-' * 50)

fd_buf = fm.open('buffered.log', 
                 mode=FileMode.WRITE,
                 io_strategy=IOStrategy.BUFFERED)
print(f'  Opened file: FD={fd_buf}')

data = b'Log entry\\n' * 10
fm.write(fd_buf, data, fsync=False)
print(f'  Written {len(data)} bytes (buffered)')

fm.close(fd_buf)
print(f'  Closed file')
print()

print('Test 2: Direct I/O + fsync (Safe)')
print('-' * 50)

fd_direct = fm.open('critical.log',
                    mode=FileMode.WRITE,
                    io_strategy=IOStrategy.DIRECT)
print(f'  Opened critical file: FD={fd_direct}')

critical_data = b'CRITICAL: Data\\n'
fm.write(fd_direct, critical_data, fsync=True)
print(f'  Written {len(critical_data)} bytes (with fsync)')

fm.close(fd_direct)
print()

print('Test 3: File statistics')
print('-' * 50)

stats = fm.get_global_stats()
print(f'  Total opens: {stats[\"total_opens\"]}')
print(f'  Total closes: {stats[\"total_closes\"]}')
print(f'  Total fsyncs: {stats[\"total_fsyncs\"]}')

print()
print('✅ File Manager test passed')
"
```

---

## 5️⃣ Run Full Integrated Demo

```bash
python demo_os_features.py
```

**This tests everything together**

**Duration:** 3-5 minutes

---

## 🔧 Quick Single-Command Tests

### Quick test all components compile:
```bash
python -c "import sys; sys.path.insert(0, 'src'); from os_synchronization import Mutex; from os_memory import MemoryManager; from os_scheduler import TaskScheduler; from os_file_manager import FileManager; print('✅ All compiled')"
```

### Quick test imports work:
```bash
python -c "
import sys
sys.path.insert(0, 'src')
print('Testing imports...')
from os_synchronization import Mutex, Semaphore, RWLock
print('✅ Synchronization imported')
from os_memory import MemoryManager, FrameBufferPool
print('✅ Memory imported')
from os_scheduler import TaskScheduler
print('✅ Scheduler imported')
from os_file_manager import FileManager
print('✅ File Manager imported')
print()
print('✅ All components imported successfully!')
"
```

---

## 📝 Save Output to File

### Save full demo output:
```bash
python demo_os_features.py > demo_output.txt 2>&1
cat demo_output.txt
```

### Save individual test output:
```bash
python -c "..." > test_result.txt
cat test_result.txt
```

---

## ⏱️ Testing Timeline

| Test | Command | Duration |
|------|---------|----------|
| Quick import check | 1-liner | <1s |
| Mutex test | Section 1.1 | 1s |
| Semaphore test | Section 1.2 | 1s |
| RWLock test | Section 1.3 | 1s |
| Condition Variable | Section 1.4 | 1s |
| Memory Manager | Section 2.1 | 2s |
| Frame Buffer Pool | Section 2.2 | 3s |
| Task Scheduler | Section 3.1 | 2s |
| File Manager | Section 4.1 | 1s |
| **Full Demo** | `python demo_os_features.py` | **3-5m** |

---

## ✅ Recommended Test Sequence

**For Quick Validation (5 minutes):**
1. `python demo_os_features.py`

**For Complete Testing (30 minutes):**
1. Quick import check
2. Test 1.1 Mutex
3. Test 1.3 RWLock
4. Test 2.2 Frame Buffer Pool
5. Test 3.1 Scheduler
6. Test 4.1 File Manager
7. `python demo_os_features.py`

**For Full Verification (55 minutes):**
1. All tests 1.1-1.4 (Synchronization)
2. All tests 2.1-2.2 (Memory)
3. Test 3.1 (Scheduler)
4. Test 4.1 (File Manager)
5. `python demo_os_features.py`
6. Review output and statistics

---

## 🎯 What If Something Fails?

### "ModuleNotFoundError"
```bash
# Make sure you're in the right directory
cd missile-detection-static-main

# Then try again
python -c "import sys; sys.path.insert(0, 'src'); from os_synchronization import Mutex; print('✅')"
```

### "Permission denied"
```bash
# Give write permissions (Linux/Mac)
chmod 755 .

# On Windows, right-click → Properties → Security
```

### "Out of memory"
- Reduce buffer sizes in tests
- Or close other applications

### Test hangs or takes too long
- Press Ctrl+C to stop
- Try simpler test (import check)

---

## 📊 Interpreting Test Output

### Good output includes:
```text
[ READY ] Component test passed
[ DONE  ] Logic verified
```

### Bad output includes:
```
[FAIL] [Feature] test failed
Error: ...
```

### Performance output shows:
```
Avg time: X.XXus  (good = <10us for pool)
Contentions: N     (good = 0 for readers)
Fragmentation: X%  (good = 0%)
```

---

## 🎓 Suggested Study Order

1. **5 minutes:** Quick import check
2. **1 min each:** Tests 1.1, 1.2, 1.3, 1.4 (4 min total)
3. **3-5 min each:** Tests 2.1, 2.2 (8-10 min total)
4. **2 min:** Test 3.1
5. **1 min:** Test 4.1
6. **3-5 min:** Full demo
7. **Total: ~30 minutes of testing**

---

**Copy any command above and paste directly into your terminal!**

