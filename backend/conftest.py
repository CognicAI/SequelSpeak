"""
Pytest configuration for SequelSpeak backend tests.
"""
import os

# MUST be set BEFORE any imports from the project
os.environ['RATE_LIMIT_ENABLED'] = 'False'

import pytest
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
