"""Test script that mimics Claude Desktop's MCP client."""
import json
import subprocess
import sys
import time

# Start the MCP server
env = {
    "SERVER_TYPE": "stdio",
    "M8FLOW_API_URL": "http://localhost:6840",
    "KEYCLOAK_URL": "http://localhost:6842",
    "KEYCLOAK_REALM": "m8flow",
    "CLIENT_ID": "m8flow-mcp",
    "KEYCLOAK_USERNAME": "admin",
    "KEYCLOAK_PASSWORD": "admin",
    "DEFAULT_TENANT_ID": "AOT",
    "LOG_LEVEL": "ERROR",
    "PYTHONPATH": ".",
}

print("Starting m8flow MCP server...")
proc = subprocess.Popen(
    [r"C:\Users\DELL\AppData\Local\Python\pythoncore-3.14-64\python.exe", "mcp-server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=env,
    cwd=r"C:\AOT\forms-flow-ai-ee\m8flow-mcp-proper"
)

try:
    # Send initialize request
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }
    }

    print(f"Sending: {json.dumps(init_request)}")
    proc.stdin.write(json.dumps(init_request) + "\n")
    proc.stdin.flush()

    # Wait for response (with timeout)
    print("Waiting for response...")
    time.sleep(3)

    # Check if process is still alive
    if proc.poll() is None:
        print("✅ Server is running!")

        # Try to read response
        try:
            # Read with timeout
            import select
            if sys.platform != 'win32':
                ready = select.select([proc.stdout], [], [], 2)
                if ready[0]:
                    response = proc.stdout.readline()
                    print(f"Response: {response}")
            else:
                # Windows doesn't support select on pipes
                print("(Windows: can't read response non-blocking)")
        except Exception as e:
            print(f"Error reading response: {e}")
    else:
        print(f"❌ Server exited with code: {proc.returncode}")
        stderr = proc.stderr.read()
        print(f"STDERR:\n{stderr}")

finally:
    proc.terminate()
    proc.wait()
    print("\nServer terminated")
