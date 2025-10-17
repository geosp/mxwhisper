#!/usr/bin/env python3
"""
Test Temporal connectivity
"""
import asyncio
import socket
from temporalio.client import Client
from app.config import settings
import pytest

def check_host_reachability(host, port):
    """Check if host is reachable on the given port."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

@pytest.mark.asyncio
async def test_temporal_connection():
    """Test connection to Temporal server."""
    print(f"🔗 Testing Temporal connectivity to: {settings.temporal_host}")

    # Parse the host and port from the URL
    if settings.temporal_host.startswith("http://"):
        host_port = settings.temporal_host.replace("http://", "")
    elif settings.temporal_host.startswith("https://"):
        host_port = settings.temporal_host.replace("https://", "")
    else:
        host_port = settings.temporal_host

    if ":" in host_port:
        host, port_str = host_port.split(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            print(f"❌ Invalid port in temporal_host: {port_str}")
            return False
    else:
        host = host_port
        port = 7233  # Default Temporal port

    print(f"🌐 Checking reachability of {host}:{port}...")
    if not check_host_reachability(host, port):
        print(f"❌ Host {host}:{port} is not reachable!")
        print("   Possible issues:")
        print("   - Temporal server is not running")
        print("   - Network connectivity problems")
        print("   - Firewall blocking the connection")
        return False

    print(f"✅ Host {host}:{port} is reachable")

    try:
        print("🔗 Connecting to Temporal server...")
        client = await Client.connect(settings.temporal_host)
        print("✅ Successfully connected to Temporal!")

        # Try to get some basic info
        try:
            workflows = client.list_workflows()
            count = 0
            async for workflow in workflows:
                count += 1
                if count >= 3:  # Show up to 3 workflows
                    break
            print(f"📋 Found {count} workflow(s) in Temporal")
        except Exception as e:
            print(f"⚠️  Connected but couldn't list workflows: {e}")
            print("   This might be normal if no workflows exist yet")

        # Note: Client doesn't have a close method in newer versions
        return True

    except Exception as e:
        print(f"❌ Failed to connect to Temporal: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_temporal_connection())
    if success:
        print("\n🎉 Temporal connectivity test PASSED!")
        print("The Temporal server is running and accessible.")
    else:
        print("\n💥 Temporal connectivity test FAILED!")
        print("To fix this:")
        print("1. Ensure Temporal server is running on the configured host")
        print("2. Check network connectivity to the Temporal host")
        print("3. Verify the TEMPORAL_HOST setting in .env file")
        print("4. For local development, you can run: temporal server start-dev")