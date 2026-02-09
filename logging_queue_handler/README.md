# Logging QueueHandler + QueueListener with C Extension

This project demonstrates how to use Python's `QueueHandler` and `QueueListener` with a custom C extension handler for high-performance logging.

## Architecture

```
Application Code
     |
     v
Logger + QueueHandler ---> Queue ---> QueueListener ---> CustomHandler(C Extension) ---> File
```

## Benefits

1. **Thread-safe logging** - No locks needed in application code
2. **Non-blocking** - Log calls return immediately
3. **High-performance** - C extension for fast I/O
4. **Scalable** - Handles high throughput gracefully

## Files

| File | Description |
|------|-------------|
| `custom_handler.c` | C extension source code |
| `custom_handler.py` | Python fallback version |
| `setup.py` | Build script for C extension |
| `logging_config.py` | Configuration module with QueueHandler/QueueListener |
| `example.py` | Usage examples |

## Quick Start

### 1. Compile the C Extension

```bash
# Build and install in-place
python setup.py build_ext --inplace

# Or install system-wide
python setup.py install
```

### 2. Run the Examples

```bash
# Run all examples
python example.py

# Run individual examples
python logging_config.py  # Run the demo
```

### 3. Use in Your Application

```python
import logging
from logging_config import LoggingConfig, create_async_logger

# Method 1: Using LoggingConfig class
config = LoggingConfig(
    log_file='app.log',
    level=logging.DEBUG
)
logger = config.register_logger('myapp')
config.start()

# Log messages (non-blocking)
logger.info('Application started')
logger.error('An error occurred')

# Cleanup
config.stop()

# Method 2: Using convenience function
logger, config = create_async_logger(
    name='myapp',
    log_file='app.log',
    level=logging.DEBUG
)

logger.info('Quick setup!')

# Don't forget to stop
config.stop()
```

## How It Works

### QueueHandler
- Intercepts log calls from your application
- Puts log records into a thread-safe queue
- Returns immediately without blocking

### QueueListener
- Runs in a separate thread
- Reads log records from the queue
- Passes records to handlers for processing

### Custom Handler
- Processes log records
- Formats and writes to file
- Implemented in C for performance (with Python fallback)

## Features

- **Buffered writes** - Multiple log messages are batched for better I/O performance
- **Exception handling** - Full exception tracebacks are logged
- **Multiple loggers** - Support for different loggers with different configurations
- **Thread-safe** - Safe to use from multiple threads without additional synchronization

## Requirements

- Python 3.6+
- A C compiler (for C extension)
  - Windows: Visual Studio or MinGW
  - Linux: gcc
  - macOS: Xcode

## Troubleshooting

### C Extension Not Compiled

If you see:
```
✗ C extension not available, using Python fallback
```

The Python fallback will be used automatically. For better performance, compile the C extension.

### Windows Build Issues

On Windows, you may need to specify the compiler:
```bash
# Using Visual Studio
python setup.py build_ext --inplace

# Using MinGW
python setup.py build_ext --inplace --compiler=mingw32
```

### Queue Full

If the queue becomes full (default size: 10000), new log messages will be dropped. Increase the queue size:

```python
config = LoggingConfig(
    log_file='app.log',
    queue_size=50000  # Increase from default
)
```
