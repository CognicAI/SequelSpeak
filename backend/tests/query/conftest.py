import pytest
from typing import Generator

@pytest.fixture(autouse=True)
def fast_orchestrator() -> Generator[None, None, None]:
    """
    Globally removes simulated `asyncio.sleep` delays from the orchestrator 
    during query endpoint tests. This prevents Starlette's `ASGITransport` from 
    hanging on background tasks.
    """
    from services.orchestrator import STAGE_DELAY
    
    # Store original times
    original_delays = STAGE_DELAY.copy()
    
    # Zero out delays for fast testing
    for key in STAGE_DELAY:
        STAGE_DELAY[key] = 0.0
        
    yield
    
    # Restore after the test finishes
    STAGE_DELAY.update(original_delays)
