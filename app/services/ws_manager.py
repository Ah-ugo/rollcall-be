from collections import defaultdict
from fastapi import WebSocket

class Manager:
    def __init__(self):
        self.rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def join(self, room: str, ws: WebSocket):
        await ws.accept()
        self.rooms[room].add(ws)

    def leave(self, room: str, ws: WebSocket):
        self.rooms[room].discard(ws)

    async def broadcast(self, room: str, message: dict):
        for ws in list(self.rooms[room]):
            try:
                await ws.send_json(message)
            except Exception:
                self.leave(room, ws)

manager = Manager()
