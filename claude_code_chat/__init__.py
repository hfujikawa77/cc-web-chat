"""
Claude Code Chat - Chat-based Web UI for Claude Code CLI

A web-based chat interface that enables smartphone control of Claude Code 
running on WSL environments with session-based directory management.
"""

__version__ = "1.0.0"
__author__ = "Claude Code Chat Team"
__email__ = "support@example.com"

from .server import main

__all__ = ["main"]