import re
from typing import Any

# Sensitive fields in UserContext that must never appear in logs.
# These fields are stored in ConversationState but excluded from all log output.
SENSITIVE_USER_CONTEXT_FIELDS: frozenset[str] = frozenset({"ip_address"})


def sanitize_user_context_for_log(user_context: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of user_context with all sensitive fields removed.

    Use this helper whenever logging user/session metadata. The full
    dict (including sensitive fields) can be persisted to ConversationState.

    Sensitive fields excluded: ip_address

    Args:
        user_context: Raw user context dictionary from UserContext.model_dump().

    Returns:
        Dict safe for logging (no ip_address or other sensitive keys).
    """
    return {k: v for k, v in user_context.items() if k not in SENSITIVE_USER_CONTEXT_FIELDS}


def mask_connection_url(url: str) -> str:
    """
    Masks the password in a database connection URL.
    Supports postgres:// and postgresql:// schemes.
    Can handle standalone URLs or error messages containing URLs.
    
    Args:
        url (str): The connection URL or string containing it.
        
    Returns:
        str: The string with the password replaced by '******'.
    """
    if not url or not isinstance(url, str):
        return str(url)
        
    # Regex to find the password part: //username:password@
    # Pattern: ://username:password@
    # We capture (://[^:]+:) to keep scheme://user: and (@) to keep @host
    # The middle part is the password.
    # Regex breakdown:
    # (://[^:@/]+)   : Matches '://' followed by username (non-colon, non-at, non-slash)
    # :              : The separator
    # ([^@]+)        : The password (until @)
    # @              : The separator
    
    # We use a pattern that matches the full structure to be safe.
    # postgres(ql)?://
    pattern = r"(postgres(?:ql)?://[^:]+):([^@]+)@"
    
    # Perform substitution; if no match is found, url is returned unchanged.
    return re.sub(pattern, r"\1:******@", url)
