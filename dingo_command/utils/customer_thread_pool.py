import os
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import threading
import time

# 队列的线程池
class QueuedThreadPool:

    # 初始化带着队列的线程池 设置线程数、队列大小
    def __init__(self, max_workers = min(32, (os.cpu_count() or 1) * 4), max_queue_size=1000):
        print(f"init thread pool max_workers: {max_workers}")
        self.executor = ThreadPoolExecutor(max_workers)
        self.task_queue = Queue(maxsize=max_queue_size)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._active_tasks = 0
        self._dispatcher_thread = threading.Thread(
            target=self._dispatch_tasks,
            daemon=True
        )
        self._dispatcher_thread.start()

    def submit(self, fn, *args, **kwargs):
        """提交任务到队列（阻塞直到有空位）"""
        if self._stop_event.is_set():
            raise RuntimeError("Pool is shutting down")
        self.task_queue.put((fn, args, kwargs))
        # print(f"after submit task_queue size: {self.task_queue.qsize()}")

    def _dispatch_tasks(self):
        """从队列取任务并提交到线程池"""
        while not self._stop_event.is_set():
            # 加锁检查
            with self._lock:
                # 检查线程池容量
                # print(f"check task_queue size: {self.task_queue.qsize()}")
                if self._active_tasks >= self.executor._max_workers:
                    time.sleep(0.5)
                    continue
            try:
                fn, args, kwargs = self.task_queue.get(timeout=0.1)
                with self._lock:
                    self._active_tasks += 1
                future = self.executor.submit(fn, *args, **kwargs)
                future.add_done_callback(self._task_completed)
            except Exception as e:
                print(e)
                continue

    def _task_completed(self, future):
        """任务完成回调"""
        with self._lock:
            self._active_tasks -= 1
            # print(f"after task completed task_queue size: {self.task_queue.qsize()}")
        self.task_queue.task_done()

    def wait_all(self, timeout=None):
        """等待队列和线程池都空闲"""
        start = time.time()
        while not self._stop_event.is_set():
            if self.task_queue.empty() and self.executor._work_queue.empty():
                return True
            if timeout and (time.time() - start) > timeout:
                return False
            time.sleep(0.1)
        return False

    def shutdown(self, wait=True):
        """优雅关闭"""
        self._stop_event.set()
        if wait:
            self.wait_all(timeout=30)
        self.executor.shutdown(wait=wait)


# 定义线程池
queuedThreadPool = QueuedThreadPool()