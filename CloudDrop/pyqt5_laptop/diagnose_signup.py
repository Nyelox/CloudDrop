import sys
import os

# Add current directory to path so we can import Server
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    import Server.Database_connection
    print(f"Database_connection file: {Server.Database_connection.__file__}")
    
    # We expect this to fail if DB is not reachable, but we want to see if we even get there
    # or if handle_signup returns something weird before DB access if mocked (unlikely)
    try:
        result = Server.Database_connection.handle_signup("diagnose_user", "diagnose_pass")
        print(f"Result type: {type(result)}")
        print(f"Result value: {result}")
    except Exception as e:
        print(f"Error calling handle_signup: {e}")

except Exception as e:
    print(f"Import error: {e}")
