"""One atomic request reservation pool shared by every stage in a round."""

import asyncio


class CallBudget:
    def __init__(self, used_calls):
        self.remaining = min(6, max(0, 12 - used_calls))
        self._lock = asyncio.Lock()

    async def reserve(self):
        async with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True
