
from urllib.parse import urlparse
import sys

# The URL provided by the user
url = "postgresql://postgres.pnxkaejzfiminoghwwqq:[YOUR-PASSWORD]@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"

print(f"Testing URL: {url}")

try:
    parsed = urlparse(url)
    print("Parsing successful!")
    print(f"Scheme: {parsed.scheme}")
    print(f"Netloc: {parsed.netloc}")
    print(f"Username: {parsed.username}")
    print(f"Password: {parsed.password}")
    print(f"Hostname: {parsed.hostname}")
    print(f"Port: {parsed.port}")
except Exception as e:
    print(f"Parsing Failed with error: {e}")
    # Print the type of exception to be sure
    print(f"Exception Type: {type(e)}")

# Test without brackets to compare
url_clean = "postgresql://postgres.pnxkaejzfiminoghwwqq:YOURPASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"
print(f"\nTesting Clean URL: {url_clean}")
try:
    parsed = urlparse(url_clean)
    print("Parsing successful!")
    print(f"Hostname: {parsed.hostname}")
except Exception as e:
    print(f"Clean Parsing Failed: {e}")
