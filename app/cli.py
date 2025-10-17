#!/usr/bin/env python3
"""
MxWhisper CLI - Command line interface for MxWhisper API server
"""
import argparse
import sys
import uvicorn
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings
from app.logging_config import setup_logging

def main():
    """Main CLI entry point for MxWhisper."""
    parser = argparse.ArgumentParser(
        description="MxWhisper API Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mxwhisper                    # Start server with default settings
  mxwhisper --host 0.0.0.0     # Bind to all interfaces
  mxwhisper --port 3001        # Use custom port
  mxwhisper --reload           # Enable auto-reload for development
  mxwhisper --workers 4        # Use multiple workers
        """
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the server to (default: 127.0.0.1)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to (default: 8000)"
    )

    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of worker processes (default: 1)"
    )

    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Logging level (default: info)"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(
        level=args.log_level.upper(),
        format_type="text",
        log_file="logs/mxwhisper.log"
    )

    print("🚀 Starting MxWhisper API Server")
    print(f"   Host: {args.host}")
    print(f"   Port: {args.port}")
    print(f"   Workers: {args.workers}")
    print(f"   Reload: {args.reload}")
    print(f"   Log Level: {args.log_level}")
    print()

    # Start the server
    try:
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            workers=args.workers,
            log_level=args.log_level,
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n👋 MxWhisper API Server stopped")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()