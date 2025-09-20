
# This module provides call-specific logging for tracking individual voice call sessions with detailed information.
#
# Key Features:
# - Thread-safe logging for concurrent calls
# - Individual log files per call session
# - Automatic log directory creation and management
#
# Log File Location:
# - All call logs are stored in: logs/calls/
# - File naming: call_[CALL_SID]_[TIMESTAMP].log
# - Generic logs (no call_sid): logs/calls/generic_call.log
#
# Functions:
# - get_call_logger(call_sid, lead_id): Get logger for specific call
# - get_call_logger(): Get generic logger when no call context available
#
# Log Levels:
# - File: DEBUG level (detailed debugging information)
# - Console: INFO level (less verbose for monitoring)
#
# Integration:
# - Used throughout websocket_handler, call_routes, data_extraction
# - Correlates with Twilio Call SID for call tracking
# - Links to database Lead ID for customer correlation

import os
import logging
from datetime import datetime
import threading

# Thread-local storage to keep track of loggers per call
_thread_local = threading.local()

# Ensure the logs directory exists
os.makedirs("logs/calls", exist_ok=True)

def get_call_logger(call_sid=None, lead_id=None):
    # If no call_sid is provided, return a generic logger
    if not call_sid:
        return _get_generic_logger()
    
    # Check if we already have a logger for this thread/call
    if hasattr(_thread_local, 'logger') and _thread_local.logger_call_sid == call_sid:
        return _thread_local.logger
    
    # Create a new logger
    logger_name = f"call_{call_sid}"
    logger = logging.getLogger(logger_name)
    
    # Only configure the logger if it's new
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        # Create a unique filename for this call
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        call_id_short = call_sid[-12:] if call_sid else "unknown"  # Use last 12 chars of call_sid
        lead_id_info = f"_lead_{lead_id}" if lead_id else ""
        log_filename = f"logs/calls/{timestamp}_call_{call_id_short}{lead_id_info}.log"
        
        # Create file handler
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.DEBUG)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)  # Less verbose on console
        
        # Create formatter
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [Call: %(name)s] %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # Make sure this logger doesn't propagate to the root logger
        logger.propagate = False
        
        # Store in thread local storage
        _thread_local.logger = logger
        _thread_local.logger_call_sid = call_sid
        _thread_local.log_filename = log_filename
        
        # Log the start of a new call log
        logger.info(f"Starting new call log for Call SID: {call_sid}, Lead ID: {lead_id}")
    
    return logger

def _get_generic_logger():
    # Get a generic logger for when no call_sid is available
    logger = logging.getLogger("generic_call")
    
    # Only configure the logger if it's new
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        # Create a unique filename for generic logs
        timestamp = datetime.now().strftime("%Y%m%d")
        log_filename = f"logs/calls/{timestamp}_generic.log"
        
        # Create file handler
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.DEBUG)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # Make sure this logger doesn't propagate to the root logger
        logger.propagate = False
    
    return logger

def get_current_log_filename():
    #Get the filename of the current call log
    if hasattr(_thread_local, 'log_filename'):
        return _thread_local.log_filename
    return None