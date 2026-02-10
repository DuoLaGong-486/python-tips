"""
Example: QueueHandler + QueueListener + Custom C Extension Handler
==================================================================

This example demonstrates how to use Python's QueueHandler and QueueListener
with a custom C extension handler for high-performance logging.

Architecture:
------------
    Application Code
         |
         v
    Logger + QueueHandler ---> Queue ---> QueueListener ---> CustomHandler ---> File

Benefits:
---------
1. Thread-safe logging - no locks needed in application code
2. Non-blocking - log calls return immediately
3. High-performance - C extension for fast I/O
4. Scalable - handles high throughput gracefully

Usage:
------
1. First, compile the C extension:
   python setup.py build_ext --inplace

2. Run this example:
   python example.py
"""
import logging
import sys
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# Add the current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

# Import our logging configuration
from logging_config import LoggingConfig, create_async_logger


def example_basic_usage():
    """Basic usage of QueueHandler/QueueListener."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Usage")
    print("=" * 60)
    
    # Create logging configuration
    config = LoggingConfig(
        log_file='basic_example.log',
        level=logging.DEBUG
    )
    
    # Register a logger
    logger = config.register_logger('myapp')
    
    # Start the listener
    config.start()
    
    # Log some messages - these will be queued and processed asynchronously
    logger.info('Application starting')
    logger.debug('Debug information')
    logger.warning('A warning occurred')
    logger.error('An error occurred')
    
    # Give some time for messages to be processed
    time.sleep(0.5)
    
    # Stop
    config.stop()
    
    print(f"\nHandler stats: {config.get_handler_stats()}")
    print("Log file: basic_example.log")


def example_multithreaded():
    """Demonstrate thread-safe logging in multi-threaded scenario."""
    print("\n" + "=" * 60)
    print("Example 2: Multi-threaded Logging")
    print("=" * 60)
    
    # Create logging configuration
    config = LoggingConfig(
        log_file='multithreaded_example.log',
        level=logging.DEBUG,
        queue_size=10000
    )
    
    # Create a logger for worker threads
    worker_logger = config.register_logger('worker')
    
    # Start the listener
    config.start()
    
    def worker_thread(thread_id):
        """Worker function that logs messages."""
        for i in range(10):
            worker_logger.info(f'Thread {thread_id}: Processing item {i}')
            worker_logger.debug(f'Thread {thread_id}: Debug details for item {i}')
            time.sleep(0.05)
        worker_logger.info(f'Thread {thread_id}: Completed')
    
    # Create multiple worker threads
    threads = []
    for i in range(4):
        t = threading.Thread(target=worker_thread, args=(i,))
        threads.append(t)
    
    # Start all threads
    print("Starting 4 worker threads...")
    for t in threads:
        t.start()
    
    # Wait for all threads to complete
    for t in threads:
        t.join()
    
    print("All threads completed.")
    
    # Give time for final messages
    time.sleep(0.5)
    
    # Stop
    config.stop()
    
    print(f"\nHandler stats: {config.get_handler_stats()}")
    print("Log file: multithreaded_example.log")


def example_with_exception():
    """Demonstrate exception logging."""
    print("\n" + "=" * 60)
    print("Example 3: Exception Logging")
    print("=" * 60)
    
    config = LoggingConfig(
        log_file='exception_example.log',
        level=logging.DEBUG
    )
    
    logger = config.register_logger('exceptions')
    config.start()
    
    try:
        logger.info('About to perform a calculation...')
        result = 10 / 0  # This will raise an exception
    except Exception as e:
        logger.exception(f'Error occurred: {e}')
    
    logger.info('Application continuing...')
    
    time.sleep(0.5)
    config.stop()
    
    print("Log file: exception_example.log")
    print("Check the log file to see the exception traceback.")


def example_high_throughput():
    """Demonstrate high-throughput logging."""
    print("\n" + "=" * 60)
    print("Example 4: High Throughput Logging")
    print("=" * 60)
    
    config = LoggingConfig(
        log_file='throughput_example.log',
        level=logging.DEBUG,
        queue_size=50000
    )
    
    logger = config.register_logger('throughput')
    config.start()
    
    # Generate many log messages quickly
    print("Generating 1000 log messages...")
    start_time = time.time()
    
    for i in range(1000):
        logger.info(f'Message {i}')
    
    # Wait for all messages to be processed
    time.sleep(1)
    
    elapsed = time.time() - start_time
    
    config.stop()
    
    print(f"Generated 1000 messages in {elapsed:.3f} seconds")
    print(f"Handler stats: {config.get_handler_stats()}")
    print("Log file: throughput_example.log")


def example_convenience_function():
    """Use the convenience function for quick setup."""
    print("\n" + "=" * 60)
    print("Example 5: Convenience Function")
    print("=" * 60)
    
    # Quick setup with convenience function
    logger, config = create_async_logger(
        name='quick',
        log_file='convenience_example.log',
        level=logging.DEBUG
    )
    
    logger.info('Quick setup logging')
    logger.warning('This was easy to set up')
    logger.debug('Debugging is easy too')
    
    time.sleep(0.5)
    
    # Cleanup
    config.stop()
    
    print("Log file: convenience_example.log")


def example_multiple_loggers():
    """Demonstrate multiple loggers with different configurations."""
    print("\n" + "=" * 60)
    print("Example 6: Multiple Loggers")
    print("=" * 60)
    
    # Create separate configurations for different loggers
    config1 = LoggingConfig(
        log_file='app.log',
        level=logging.DEBUG
    )
    
    config2 = LoggingConfig(
        log_file='errors.log',
        level=logging.WARNING
    )
    
    # Register loggers
    app_logger = config1.register_logger('application')
    error_logger = config2.register_logger('errors')
    
    # Start both listeners
    config1.start()
    config2.start()
    
    # Log messages
    app_logger.info('Application started')
    app_logger.debug('Debug info')
    
    error_logger.warning('This is a warning')
    error_logger.error('This is an error')
    
    # Errors also go to app log
    app_logger.error('This error goes to app.log')
    
    time.sleep(0.5)
    
    # Stop
    config1.stop()
    config2.stop()
    
    print("Log files: app.log, errors.log")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("QueueHandler + QueueListener + C Extension Handler Demo")
    print("=" * 60)
    
    # Check for C extension
    try:
        from custom_handler import CustomHandler
        print("[OK] C extension is available")
    except ImportError:
        print("[X] C extension not available, using Python fallback")
        print("  To compile C extension, run:")
        print("  python setup.py build_ext --inplace")
    
    # Run examples
    try:
        example_basic_usage()
        example_multithreaded()
        example_with_exception()
        example_high_throughput()
        example_convenience_function()
        example_multiple_loggers()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)
    print("\nGenerated log files:")
    print("  - basic_example.log")
    print("  - multithreaded_example.log")
    print("  - exception_example.log")
    print("  - throughput_example.log")
    print("  - convenience_example.log")
    print("  - app.log")
    print("  - errors.log")


if __name__ == '__main__':
    main()
