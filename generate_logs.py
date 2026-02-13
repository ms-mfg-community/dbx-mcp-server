import os
import random
from datetime import datetime, timedelta, timezone

# Create logs directory
os.makedirs('mock_logs', exist_ok=True)

# Sample data for realistic log generation
ERROR_CODES = [
    'CC-1001', 'CC-1002', 'CC-1003', 'CC-1004', 'CC-1005',
    'CC-2001', 'CC-2002', 'CC-2003', 'CC-2004', 'CC-2005',
    'CC-3001', 'CC-3002', 'CC-3003', 'CC-3004', 'CC-3005',
    'CC-4001', 'CC-4002', 'CC-4003', 'CC-4004', 'CC-4005',
    'CC-5001', 'CC-5002', 'CC-5003', 'CC-5004', 'CC-5005',
]

FILE_PATHS = [
    'app/src/main.py',
    'app/src/database.py',
    'app/src/auth.py',
    'app/src/handlers.py',
    'app/src/utils.py',
    'app/src/config.py',
    'app/api/endpoints.py',
    'app/api/middleware.py',
    'app/services/cache.py',
    'app/services/queue.py',
    'app/models/user.py',
    'app/models/product.py',
    'app/models/order.py',
    'app/tests/test_auth.py',
    'app/tests/test_api.py',
    'scripts/deploy.py',
    'scripts/migrate.py',
]

SEVERITIES = ['Warning', 'Error', 'Event']

ERROR_MESSAGES = [
    'Database connection timeout after 30 seconds',
    'Failed to authenticate user credentials',
    'Memory allocation failed: insufficient heap space',
    'Network socket error: connection refused',
    'Invalid JSON payload in request body',
    'Cache miss for key: {key}',
    'Transaction rollback due to deadlock',
    'File not found: {filename}',
    'Permission denied: insufficient privileges',
    'API rate limit exceeded: {limit} requests/min',
    'SSL certificate validation failed',
    'Configuration parameter missing: {param}',
    'Unhandled exception in worker thread',
    'Queue processing timeout exceeded',
    'Data validation failed: invalid format',
    'Resource exhausted: max connections reached',
    'Service dependency unavailable',
    'Index out of bounds exception',
    'Type casting error: incompatible types',
    'Circular import detected in module',
    'Regex compilation error: invalid pattern',
    'Null pointer exception: object is None',
    'Integer overflow detected',
    'Stack overflow in recursive function',
    'Corrupted data in storage backend',
]


def generate_timestamp_seconds_back(max_seconds=604800):
    """Generate a random timestamp within the last max_seconds"""
    now = datetime.now(timezone.utc)
    seconds_back = random.randint(0, max_seconds)
    return now - timedelta(seconds=seconds_back)


def generate_log_entry():
    """Generate a single log entry"""
    timestamp = generate_timestamp_seconds_back()
    error_code = random.choice(ERROR_CODES)
    file_path = random.choice(FILE_PATHS)
    severity = random.choice(SEVERITIES)
      
    # Select and format error message
    message_template = random.choice(ERROR_MESSAGES)
    if '{key}' in message_template:
        cache_key = f'cache_{random.randint(1000, 9999)}'
        message = message_template.format(key=cache_key)
    elif '{filename}' in message_template:
        message = message_template.format(
            filename=random.choice(FILE_PATHS))
    elif '{param}' in message_template:
        params = ['db_host', 'api_key', 'timeout', 'max_retries']
        message = message_template.format(param=random.choice(params))
    elif '{limit}' in message_template:
        message = message_template.format(
            limit=random.randint(100, 1000))
    else:
        message = message_template
    
    return {
        'timestamp': timestamp.isoformat() + 'Z',
        'error_code': error_code,
        'file': file_path,
        'severity': severity,
        'message': message
    }


def format_log_line(log_entry):
    """Format log entry as tab-separated line"""
    return (
        f"{log_entry['timestamp']}\t{log_entry['error_code']}\t"
        f"{log_entry['file']}\t{log_entry['severity']}\t"
        f"{log_entry['message']}"
    )


# Generate 200 log files
num_files = 200
print(f"Generating {num_files} mock log files...")

for i in range(1, num_files + 1):
    # Generate 5-15 log entries per file
    num_entries = random.randint(5, 15)
    
    filename = f"mock_logs/app_error_log_{i:03d}.log"
    
    with open(filename, 'w') as f:
        # Add a header
        f.write("# Application Error Log\n")
        f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}Z\n")
        f.write("# Format: TIMESTAMP\tERROR_CODE\tFILE\tSEVERITY\tMESSAGE\n")
        f.write("-" * 120 + "\n")
        
        # Generate log entries
        for entry_num in range(num_entries):
            log_entry = generate_log_entry()
            f.write(format_log_line(log_entry) + "\n")
    
    if (i) % 50 == 0:
        print(f"  Generated {i} files...")

print(f"\n✓ Successfully generated {num_files} mock log files in"
      f" 'mock_logs' directory")
print("\nLog file format:")
print("  - Location: mock_logs/app_error_log_001.log through")
print("    app_error_log_200.log")
print("  - Format: TIMESTAMP (UTC) | ERROR_CODE (CC-XXXX) | FILE")
print("    (path) | SEVERITY (Warning/Error/Event) | MESSAGE")
print("\nReady for upload to Databricks!")
