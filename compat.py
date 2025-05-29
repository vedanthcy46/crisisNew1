"""
Compatibility module for handling deprecated functions.
"""
import hmac

# Provide safe_str_cmp that was removed from werkzeug.security
def safe_str_cmp(a, b):
    """This function compares strings in constant time."""
    return hmac.compare_digest(a, b)