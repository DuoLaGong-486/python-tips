"""
Logging Configuration with QueueHandler and QueueListener
=========================================================

This module provides a complete logging configuration that uses:
- QueueHandler: Decouples log emission from log processing
- QueueListener: Processes log records from a queue in a separate thread
- Custom C Extension Handler: For high-performance log writing

This pattern is especially useful for:
- Multithreaded applications
- High-throughput logging scenarios
- Preventing I/O blocking in the main application
"""
import logging
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
import threading
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

try:
    from custom_handler import CustomHandler
    HAS_C_EXTENSION = True
except ImportError:
    from custom_handler import CustomHandler as PyCustomHandler
    HAS_C_EXTENSION = False


class LoggingConfig:
    """
    Centralized logging configuration manager.
    
    Provides a convenient interface for setting up logging with
    QueueHandler/QueueListener and custom handlers.
    """
    
    def __init__(self, 
                 log_file='app.log',
                 level=logging.DEBUG,
                 queue_size=10000,
                 use_c_extension=True,
                 formatter=None):
        """
        Initialize the logging configuration.
        
        Args:
            log_file: Path to the log file
            level: Minimum log level
            queue_size: Maximum size of the log queue
            use_c_extension: Whether to try using C extension
            formatter: Custom formatter string or None for default
        """
        self.log_file = log_file
        self.level = level
        self.queue_size = queue_size
        self.use_c_extension = use_c_extension and HAS_C_EXTENSION
        
        # Create queue for thread-safe logging
        self.log_queue = Queue(maxsize=queue_size)
        
        # Create handler
        if self.use_c_extension:
            print(f"Using C extension handler for {log_file}")
            self.handler = CustomHandler(log_file, level=level)
        else:
            print(f"Using Python fallback handler for {log_file}")
            self.handler = PyCustomHandler(log_file, level=level)
        
        # Set formatter
        if formatter:
            self.handler.setFormatter(logging.Formatter(formatter))
        else:
            # Default format matching C extension output
            default_format = '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
            self.handler.setFormatter(logging.Formatter(default_format, 
                                                        datefmt='%Y-%m-%d %H:%M:%S'))
        
        # Create queue listener for threaded processing
        self.queue_listener = QueueListener(self.log_queue, self.handler, respect_handler_level=True)
        
        # Track registered loggers
        self._loggers = {}
        self._original_handlers = {}
        self._queue_handlers = {}
    
    def register_logger(self, logger_name):
        """
        Register a logger with QueueHandler.
        
        Args:
            logger_name: Name of the logger to register
            
        Returns:
            logging.Logger: The registered logger
        """
        logger = logging.getLogger(logger_name)
        
        if logger_name not in self._loggers:
            # Store original handlers
            self._original_handlers[logger_name] = logger.handlers.copy()
            
            # Clear existing handlers and add QueueHandler
            logger.handlers = []
            queue_handler = QueueHandler(self.log_queue)
            logger.addHandler(queue_handler)
            self._queue_handlers[logger_name] = queue_handler
            
            # Set level
            logger.setLevel(self.level)
            
            self._loggers[logger_name] = logger
        
        return logger
    
    def unregister_logger(self, logger_name):
        """
        Unregister a logger and restore original handlers.
        
        Args:
            logger_name: Name of the logger to unregister
        """
        if logger_name in self._loggers:
            logger = self._loggers[logger_name]
            
            # Remove QueueHandler
            if logger_name in self._queue_handlers:
                queue_handler = self._queue_handlers[logger_name]
                logger.removeHandler(queue_handler)
                del self._queue_handlers[logger_name]
            
            # Restore original handlers
            if logger_name in self._original_handlers:
                logger.handlers = self._original_handlers[logger_name]
                del self._original_handlers[logger_name]
            
            del self._loggers[logger_name]
    
    def start(self):
        """Start the queue listener."""
        self.queue_listener.start()
    
    def stop(self):
        """Stop the queue listener and flush all pending logs."""
        # Flush handler's internal buffer
        if hasattr(self.handler, 'flush'):
            self.handler.flush()
        # Stop the listener
        self.queue_listener.stop()
    
    def flush(self):
        """Flush all pending log records."""
        # Put a sentinel to trigger flush
        self.log_queue.put(None)
    
    def get_handler_stats(self):
        """Get statistics from the handler."""
        if hasattr(self.handler, 'get_stats'):
            return self.handler.get_stats()
        return {'level': self.level, 'queue_size': self.queue_size}
    
    def setup_root_logger(self):
        """Set up the root logger with QueueHandler."""
        self.register_logger('')
    
    def configure_basic(self):
        """
        Configure basic logging with QueueHandler/QueueListener.
        
        This is a simpler alternative for quick setup.
        """
        # Create a logger with QueueHandler
        root_logger = logging.getLogger()
        
        # Add QueueHandler to root
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setLevel(self.level)
        root_logger.addHandler(queue_handler)
        
        # Add our custom handler to the listener
        self.queue_listener = QueueListener(self.log_queue, self.handler, 
                                            respect_handler_level=True)
        self.queue_listener.start()
        
        # Set root level
        root_logger.setLevel(self.level)
        
        return root_logger


def create_async_logger(name='app', log_file='async.log', level=logging.DEBUG):
    """
    Convenience function to create an async logger.
    
    Args:
        name: Logger name
        log_file: Path to log file
        level: Log level
        
    Returns:
        tuple: (logger, config) where config has stop() method
    """
    config = LoggingConfig(log_file=log_file, level=level)
    logger = config.register_logger(name)
    config.start()
    
    return logger, config


# Demonstration and test
def demo():
    """Demonstrate the logging configuration."""
    import time
    
    print("=" * 60)
    print("Logging QueueHandler/QueueListener Demo")
    print("=" * 60)
    
    # Create configuration
    config = LoggingConfig(
        log_file='demo.log',
        level=logging.DEBUG,
        queue_size=1000
    )
    
    # Register loggers
    logger1 = config.register_logger('module1')
    logger2 = config.register_logger('module2')
    
    # Start the listener
    config.start()
    
    print("\nLogging configuration started...")
    print(f"Handler stats: {config.get_handler_stats()}")
    
    # Generate some log messages
    print("\nGenerating log messages...")
    
    for i in range(5):
        logger1.debug(f'Debug message {i} from module1')
        logger1.info(f'Info message {i} from module1')
        logger1.warning(f'Warning message {i} from module1')
        logger1.error(f'Error message {i} from module1')
        
        logger2.debug(f'Debug message {i} from module2')
        logger2.info(f'Info message {i} from module2')
        
        time.sleep(0.1)
    
    # Show final stats
    print(f"\nHandler stats after logging: {config.get_handler_stats()}")
    
    # Stop
    config.stop()
    
    print(f"\nLog file contents:")
    print("-" * 40)
    if os.path.exists('demo.log'):
        with open('demo.log', 'r', encoding='utf-8') as f:
            content = f.read()
            # Show last 20 lines
            lines = content.split('\n')
            for line in lines[-20:]:
                if line.strip():
                    print(line)
    print("-" * 40)
    
    # Cleanup
    config.unregister_logger('module1')
    config.unregister_logger('module2')
    
    print("\nDemo complete!")


if __name__ == '__main__':
    demo()
