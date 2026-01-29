import re

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
