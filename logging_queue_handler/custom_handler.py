"""
Custom Logging Handler - Python Fallback Version
=================================================

This is a pure Python implementation of a custom logging handler.
Used as a fallback when the C extension is not available.

Features:
    - Thread-safe logging with QueueHandler/QueueListener
    - Custom formatting
    - Buffered writes for performance
"""
import logging
from logging import Handler
from queue import Queue
from threading import Thread, Lock
import time
import os


class CustomHandler(Handler):
    """
    Custom logging handler with C extension interface.
    
    This handler writes logs to a file with high-performance formatting.
    Compatible with QueueHandler and QueueListener patterns.
    """
    
    def __init__(self, filename, mode='a', encoding='utf-8',
                 delay=False, level=logging.DEBUG):
        """
        Initialize the custom handler.
        
        Args:
            filename: Path to the log file
            mode: File open mode ('a' for append, 'w' for overwrite)
            encoding: File encoding
            delay: Whether to delay opening the file
            level: Logging level
        """
        super().__init__(level=level)
        self.filename = filename
        self.mode = mode
        self.encoding = encoding
        self.delay = delay
        self.stream = None
        self._buffer = []
        self._buffer_size = 100
        self._buffer_lock = Lock()
        self._is_closed = False
        
        if not delay:
            self._open()
    
    def _open(self):
        """Open the log file."""
        if self.filename:
            # Ensure directory exists
            directory = os.path.dirname(self.filename)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            self.stream = open(self.filename, self.mode, encoding=self.encoding)
    
    def _close(self):
        """Close the log file."""
        if self.stream:
            try:
                self.stream.close()
            except Exception:
                pass
            self.stream = None
    
    def emit(self, record):
        """
        Process and emit a log record.
        
        Args:
            record: LogRecord object
        """
        try:
            msg = self.format(record)
            with self._buffer_lock:
                self._buffer.append(msg)
                if len(self._buffer) >= self._buffer_size:
                    self.flush()
        except Exception:
            self.handleError(record)
    
    def flush(self):
        """Flush all buffered logs to the file."""
        with self._buffer_lock:
            if self._buffer and self.stream:
                try:
                    for msg in self._buffer:
                        self.stream.write(msg + '\n')
                    self.stream.flush()
                    self._buffer.clear()
                except Exception:
                    self.handleError(None)
    
    def close(self):
        """Close the handler and release resources."""
        self.flush()
        self._close()
        self._is_closed = True
        super().close()
    
    def format(self, record):
        """
        Format the log record.
        
        Args:
            record: LogRecord object
            
        Returns:
            str: Formatted log message
        """
        # Handle exception info
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        
        # Custom format: [timestamp] [level] [name] message
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        levelname = record.levelname
        name = record.name
        message = record.getMessage()
        
        return f"[{timestamp}] [{levelname}] [{name}] {message}"
    
    def set_buffer_size(self, size):
        """
        Set the buffer size for batched writes.
        
        Args:
            size: Number of messages to buffer before flushing
        """
        if size > 0:
            self._buffer_size = size
    
    def get_stats(self):
        """
        Get handler statistics.
        
        Returns:
            dict: Handler statistics
        """
        return {
            'filename': self.filename,
            'level': self.level,
            'buffer_size': self._buffer_size,
            'buffer_count': len(self._buffer),
            'is_closed': self._is_closed
        }


class ThreadedFileHandler(Handler):
    """
    A thread-safe file handler that writes logs in a separate thread.
    
    This handler uses a Queue to decouple log writing from the main thread,
    improving performance in high-throughput scenarios.
    """
    
    def __init__(self, filename, mode='a', encoding='utf-8',
                 level=logging.DEBUG, queue_size=1000):
        """
        Initialize the threaded file handler.
        
        Args:
            filename: Path to the log file
            mode: File open mode
            encoding: File encoding
            level: Logging level
            queue_size: Maximum queue size
        """
        super().__init__(level=level)
        self.filename = filename
        self.mode = mode
        self.encoding = encoding
        self.queue = Queue(maxsize=queue_size)
        self._write_thread = None
        self._running = False
        self._stop_event = None
        self._formatter = None
        
        # Ensure directory exists
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
    
    def _writer_worker(self):
        """Background worker that writes logs to file."""
        self._stop_event = None
        
        with open(self.filename, self.mode, encoding=self.encoding) as f:
            while True:
                try:
                    # Wait for log messages with timeout
                    if self._stop_event is not None and self._stop_event.is_set():
                        # Flush remaining messages
                        while not self.queue.empty():
                            try:
                                msg = self.queue.get_nowait()
                                f.write(msg + '\n')
                                f.flush()
                            except Exception:
                                break
                        break
                    
                    # Get message from queue
                    msg = self.queue.get(timeout=0.1)
                    f.write(msg + '\n')
                    
                    # Flush every 10 messages
                    if self.queue.qsize() % 10 == 0:
                        f.flush()
                        
                except Exception:
                    # Queue is empty or stopped
                    if self._stop_event and self._stop_event.is_set():
                        break
                    continue
    
    def start(self):
        """Start the background writer thread."""
        if not self._running:
            self._running = True
            self._write_thread = Thread(target=self._writer_worker, daemon=True)
            self._write_thread.start()
    
    def stop(self):
        """Stop the background writer thread."""
        if self._running:
            self._running = False
            if self._stop_event:
                self._stop_event.set()
            if self._write_thread:
                self._write_thread.join(timeout=1.0)
    
    def emit(self, record):
        """
        Queue a log record for writing.
        
        Args:
            record: LogRecord object
        """
        if not self._running:
            self.start()
        
        try:
            msg = self.format(record)
            # Don't block if queue is full
            if not self.queue.full():
                self.queue.put_nowait(msg)
        except Exception:
            self.handleError(record)
    
    def flush(self):
        """Flush all pending logs."""
        pass  # Handled by worker thread
    
    def close(self):
        """Close the handler and stop the writer thread."""
        self.stop()
        super().close()
    
    def setFormatter(self, formatter):
        """Set the formatter."""
        self._formatter = formatter
        super().setFormatter(formatter)
    
    def format(self, record):
        """Format the log record."""
        if self._formatter:
            return self._formatter.format(record)
        
        # Default format
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        return f"[{timestamp}] [{record.levelname}] [{record.name}] {record.getMessage()}"


# Convenience function to create a custom handler
def create_handler(filename, level=logging.DEBUG, use_threaded=False):
    """
    Create a custom logging handler.
    
    Args:
        filename: Path to the log file
        level: Logging level
        use_threaded: Whether to use threaded handler
        
    Returns:
        Handler: Custom handler instance
    """
    if use_threaded:
        return ThreadedFileHandler(filename, level=level)
    return CustomHandler(filename, level=level)


if __name__ == '__main__':
    # Test the handler
    handler = CustomHandler('test_handler.log', level=logging.DEBUG)
    handler.setFormatter(logging.Formatter('%(message)s'))
    
    logger = logging.getLogger('test')
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    
    logger.debug('Debug message')
    logger.info('Info message')
    logger.warning('Warning message')
    logger.error('Error message')
    
    handler.close()
    print(f"Logs written to test_handler.log")
    print(f"Handler stats: {handler.get_stats()}")
