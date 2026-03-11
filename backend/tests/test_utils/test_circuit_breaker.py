import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch
from utils.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerError

class TestCircuitBreaker:
    @pytest.fixture
    def breaker(self):
        return CircuitBreaker(failure_threshold=2, timeout=1, name="test_breaker")

    @pytest.mark.asyncio
    async def test_initial_state(self, breaker):
        assert await breaker.get_state() == CircuitState.CLOSED
        assert await breaker.get_failure_count() == 0

    @pytest.mark.asyncio
    async def test_success_keeps_closed(self, breaker):
        mock_func = AsyncMock(return_value="success")
        result = await breaker.call(mock_func)
        assert result == "success"
        assert await breaker.get_state() == CircuitState.CLOSED
        assert await breaker.get_failure_count() == 0

    @pytest.mark.asyncio
    async def test_failure_threshold_opens_circuit(self, breaker):
        mock_func = AsyncMock(side_effect=Exception("fail"))
        
        # First failure
        with pytest.raises(Exception):
            await breaker.call(mock_func)
        assert await breaker.get_state() == CircuitState.CLOSED
        assert await breaker.get_failure_count() == 1
        
        # Second failure - should open
        with pytest.raises(Exception):
            await breaker.call(mock_func)
        assert await breaker.get_state() == CircuitState.OPEN
        assert await breaker.get_failure_count() == 2

    @pytest.mark.asyncio
    async def test_open_circuit_blocks_requests(self, breaker):
        await breaker.force_open()
        mock_func = AsyncMock()
        
        with pytest.raises(CircuitBreakerError) as excinfo:
            await breaker.call(mock_func)
        assert "Circuit breaker is open" in str(excinfo.value)
        mock_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_half_open_on_timeout(self, breaker):
        await breaker.force_open()
        # Mock time to simulate timeout passed
        with patch("utils.circuit_breaker.time.time", return_value=time.time() + 2):
            mock_func = AsyncMock(return_value="recovered")
            result = await breaker.call(mock_func)
            assert result == "recovered"
            assert await breaker.get_state() == CircuitState.CLOSED
            assert await breaker.get_failure_count() == 0

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self, breaker):
        await breaker.force_open()
        with patch("utils.circuit_breaker.time.time", return_value=time.time() + 2):
            mock_func = AsyncMock(side_effect=Exception("still failing"))
            with pytest.raises(Exception):
                await breaker.call(mock_func)
            assert await breaker.get_state() == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_manual_reset(self, breaker):
        await breaker.force_open()
        await breaker.reset()
        assert await breaker.get_state() == CircuitState.CLOSED
        assert await breaker.get_failure_count() == 0

    @pytest.mark.asyncio
    async def test_disabled_circuit_breaker(self, breaker):
        with patch("utils.circuit_breaker.settings.circuit_breaker_enabled", False):
            await breaker.force_open()
            mock_func = AsyncMock(return_value="passed through")
            result = await breaker.call(mock_func)
            assert result == "passed through"
            # Should not change state even on success if disabled
            assert await breaker.get_state() == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_should_attempt_reset_no_failure_time(self, breaker):
        # Manually clear last_failure_time
        breaker.last_failure_time = None
        assert breaker._should_attempt_reset() is True
