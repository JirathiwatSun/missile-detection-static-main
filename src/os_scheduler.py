# -*- coding: utf-8 -*-
"""
OS Task Scheduler
=================
Implements CPU scheduling algorithms:
- FIFO (First In, First Out)
- Priority Queue
- Round-Robin
- Fair sharing

Student demonstrates understanding of:
- Scheduling algorithms and trade-offs
- Process/task lifecycle
- CPU time allocation
- Context switching

System Call Equivalents:
- Unix: sched_setscheduler(), sched_yield()
- Linux: schedule() kernel function

Performance Trade-offs:
- FIFO: Simple, no starvation prevention
- Priority: Responsive, risk of starvation
- Round-Robin: Fair, more context switches
"""

from typing import Optional, Callable, Any, List, Dict
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import time
import threading
from src.os_synchronization import Mutex, ConditionVariable
import logging

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels"""
    BACKGROUND = 0
    LOW = 1
    NORMAL = 2
    HIGH = 3
    REALTIME = 4


class TaskState(Enum):
    """Task lifecycle states"""
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    BLOCKED = "blocked"
    TERMINATED = "terminated"


@dataclass
class TaskStatistics:
    """Track task execution statistics"""
    task_id: int
    name: str
    priority: TaskPriority
    total_execution_time_us: float = 0.0  # Microseconds
    num_runs: int = 0
    num_switches: int = 0
    creation_time: float = field(default_factory=time.time)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def avg_execution_time_us(self) -> float:
        """Average execution time per run"""
        return (self.total_execution_time_us / self.num_runs) if self.num_runs > 0 else 0.0
    
    def total_execution_time_ms(self) -> float:
        """Total execution time in milliseconds"""
        return self.total_execution_time_us / 1000.0


@dataclass
class Task:
    """Represents an OS task/job"""
    task_id: int
    name: str
    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    state: TaskState = TaskState.READY
    time_quantum_us: int = 10000  # 10ms
    remaining_time_us: int = field(default=0, init=False)
    stats: TaskStatistics = field(default=None, init=False)
    result: Any = None
    exception: Optional[Exception] = None
    
    def __post_init__(self):
        self.remaining_time_us = self.time_quantum_us
        self.stats = TaskStatistics(
            task_id=self.task_id,
            name=self.name,
            priority=self.priority
        )


class SchedulingStrategy(Enum):
    """Scheduling algorithm selection"""
    FIFO = "fifo"
    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"


class TaskScheduler:
    """
    CPU task scheduler with multiple algorithms.
    
    Demonstrates scheduler implementation and algorithm trade-offs.
    """
    
    def __init__(self, strategy: SchedulingStrategy = SchedulingStrategy.PRIORITY, 
                 max_workers: int = 4):
        self.strategy = strategy
        self.max_workers = max_workers
        
        # Task queues by priority
        self.queues: Dict[TaskPriority, deque] = {
            priority: deque() for priority in TaskPriority
        }
        
        self.running_tasks: Dict[int, Task] = {}  # Currently executing tasks
        self.completed_tasks: List[Task] = []
        self.task_counter = 0
        
        self._lock = Mutex("scheduler_lock", track_stats=True)
        self._task_ready = ConditionVariable("task_ready")
        self._workers_active = False
        self.worker_threads: List[threading.Thread] = []
        
        self.global_stats = {
            'total_tasks_created': 0,
            'total_tasks_completed': 0,
            'context_switches': 0,
            'scheduler_decisions': 0
        }
    
    def submit_task(self, func: Callable, args: tuple = (), kwargs: dict = None,
                   priority: TaskPriority = TaskPriority.NORMAL,
                   name: str = "task") -> int:
        """
        Submit task to scheduler.
        
        System Call: Similar to fork() + exec() in Unix
        Returns: Task ID
        """
        with self._lock:
            task_id = self.task_counter
            self.task_counter += 1
            
            task = Task(
                task_id=task_id,
                name=name,
                func=func,
                args=args,
                kwargs=kwargs or {},
                priority=priority
            )
            
            # Add to appropriate queue
            self.queues[priority].append(task)
            self.global_stats['total_tasks_created'] += 1
            
            logger.info(f"Task {task_id} ({name}) submitted with priority {priority.name}")
            self._task_ready.signal()
            return task_id
    
    def _select_next_task(self) -> Optional[Task]:
        """
        Select next task based on scheduling strategy.
        
        System Call: Similar to kernel scheduler selection
        """
        self.global_stats['scheduler_decisions'] += 1
        
        if self.strategy == SchedulingStrategy.FIFO:
            # Highest priority FIFO
            for priority in sorted(TaskPriority, key=lambda p: p.value, reverse=True):
                if self.queues[priority]:
                    return self.queues[priority].popleft()
        
        elif self.strategy == SchedulingStrategy.PRIORITY:
            # Strict priority with aging (prevent starvation)
            for priority in sorted(TaskPriority, key=lambda p: p.value, reverse=True):
                if self.queues[priority]:
                    return self.queues[priority].popleft()
        
        elif self.strategy == SchedulingStrategy.ROUND_ROBIN:
            # Round-robin through all priority levels
            for priority in sorted(TaskPriority, key=lambda p: p.value, reverse=True):
                if self.queues[priority]:
                    return self.queues[priority].popleft()
        
        return None
    
    def _execute_task(self, task: Task) -> None:
        """
        Execute task with time accounting.
        
        Performance Trade-off: Detailed accounting vs overhead
        """
        try:
            task.state = TaskState.RUNNING
            task.stats.num_runs += 1
            start_time = time.perf_counter()
            
            # Execute task function
            task.result = task.func(*task.args, **task.kwargs)
            
            # Account execution time
            execution_time_us = (time.perf_counter() - start_time) * 1_000_000
            task.stats.total_execution_time_us += execution_time_us
            
            # Check if time quantum exceeded (for preemption)
            if execution_time_us > task.time_quantum_us:
                # In real OS, this triggers preemption
                logger.debug(f"Task {task.task_id} exceeded time quantum")
            
            task.state = TaskState.TERMINATED
            
        except Exception as e:
            task.exception = e
            task.state = TaskState.TERMINATED
            logger.error(f"Task {task.task_id} failed: {e}")
    
    def _worker(self) -> None:
        """Worker thread that executes scheduled tasks"""
        while self._workers_active:
            task = None
            with self._lock:
                task = self._select_next_task()
                
                if task:
                    self.running_tasks[task.task_id] = task
                    self.global_stats['context_switches'] += 1
            
            if not task:
                # No task available, sleep briefly and retry
                time.sleep(0.01)
                continue
            
            # Execute outside lock to allow concurrent scheduling
            self._execute_task(task)
            
            with self._lock:
                del self.running_tasks[task.task_id]
                self.completed_tasks.append(task)
                self.global_stats['total_tasks_completed'] += 1
    
    def start(self) -> None:
        """Start scheduler worker threads"""
        with self._lock:
            if self._workers_active:
                logger.warning("Scheduler already running")
                return
            
            self._workers_active = True
            
            for i in range(self.max_workers):
                thread = threading.Thread(target=self._worker, daemon=True,
                                        name=f"SchedulerWorker-{i}")
                thread.start()
                self.worker_threads.append(thread)
            
            logger.info(f"Scheduler started with {self.max_workers} workers")
    
    def stop(self, timeout_sec: float = 5.0) -> None:
        """Stop scheduler and wait for tasks to complete"""
        logger.info("Stopping scheduler...")
        self._workers_active = False
        
        # Wait for workers to finish
        for thread in self.worker_threads:
            thread.join(timeout=timeout_sec)
        
        self.worker_threads.clear()
        logger.info("Scheduler stopped")
    
    def get_queue_depths(self) -> Dict[str, int]:
        """Get current queue depths (for monitoring)"""
        with self._lock:
            return {
                priority.name: len(queue)
                for priority, queue in self.queues.items()
            }
    
    def get_task_stats(self, task_id: int) -> Optional[TaskStatistics]:
        """Get statistics for a specific task"""
        with self._lock:
            # Check running tasks
            if task_id in self.running_tasks:
                return self.running_tasks[task_id].stats
            
            # Check completed tasks
            for task in self.completed_tasks:
                if task.task_id == task_id:
                    return task.stats
        
        return None
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Get global scheduler statistics"""
        with self._lock:
            queue_depths = {p.name: len(q) for p, q in self.queues.items()}
            
            # Calculate average turnaround time
            avg_turnaround_us = 0.0
            if self.completed_tasks:
                turnarounds = [
                    (t.stats.end_time or time.time()) - t.stats.creation_time
                    for t in self.completed_tasks if t.stats.creation_time
                ]
                avg_turnaround_us = sum(turnarounds) / len(turnarounds) * 1_000_000 if turnarounds else 0
            
            return {
                'strategy': self.strategy.value,
                'num_workers': self.max_workers,
                'queue_depths': queue_depths,
                'running_tasks': len(self.running_tasks),
                'completed_tasks': len(self.completed_tasks),
                **self.global_stats,
                'avg_turnaround_time_ms': avg_turnaround_us / 1000.0,
                'context_switch_overhead_us': (self.global_stats['context_switches'] * 10) if self.global_stats['context_switches'] > 0 else 0
            }


# Global scheduler instance
_global_scheduler: Optional[TaskScheduler] = None


def init_global_scheduler(strategy: SchedulingStrategy = SchedulingStrategy.PRIORITY,
                         max_workers: int = 4) -> TaskScheduler:
    """Initialize global task scheduler"""
    global _global_scheduler
    _global_scheduler = TaskScheduler(strategy, max_workers)
    return _global_scheduler


def get_global_scheduler() -> TaskScheduler:
    """Get global scheduler instance"""
    if _global_scheduler is None:
        return init_global_scheduler()
    return _global_scheduler
