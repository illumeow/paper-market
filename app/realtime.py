import asyncio


class Broadcaster:
    def __init__(self):
        self._subs = set()

    async def subscribe(self):
        q = asyncio.Queue(maxsize=100)
        self._subs.add(q)
        return q

    def unsubscribe(self, q):
        self._subs.discard(q)

    async def publish(self, event: dict):
        for q in list(self._subs):
            if not q.full():
                await q.put(event)
