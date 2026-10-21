import http.client
import threading
import time
from dataclasses import dataclass

HOST = "data.rada.gov.ua"
USER_AGENT = "OpenData"
TIMEOUT_SECONDS = 120
MIN_RATE = 0.2
SPEEDUP_AFTER = 300
DEFAULT_RETRY_AFTER = 60.0
BACKOFF_SECONDS = (5, 15, 45, 120, 300)
DDOS_SHIELD_MARKER = b"DDoS"


class Blocked(Exception):
    pass


def is_block_page(status: int, body: bytes) -> bool:
    return status == 403 and DDOS_SHIELD_MARKER in body


class Unavailable(Exception):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes


class Pacer:
    def __init__(self, rate: float, max_rate: float) -> None:
        self.rate = rate
        self._max_rate = max_rate
        self._lock = threading.Lock()
        self._next_slot = time.monotonic()
        self._streak = 0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + 1 / self.rate
        time.sleep(slot - now)

    def succeeded(self) -> None:
        with self._lock:
            self._streak += 1
            if self._streak >= SPEEDUP_AFTER:
                self.rate = min(self._max_rate, self.rate * 1.1)
                self._streak = 0

    def throttled(self, pause_seconds: float) -> None:
        with self._lock:
            self.rate = max(MIN_RATE, self.rate / 2)
            self._streak = 0
            self._next_slot = time.monotonic() + pause_seconds


class RadaClient:
    def __init__(self, pacer: Pacer) -> None:
        self._pacer = pacer
        self._local = threading.local()

    def get(self, path: str) -> Response:
        for backoff in BACKOFF_SECONDS:
            self._pacer.wait()
            connection = self._connection()
            try:
                connection.request("GET", path, headers={"User-Agent": USER_AGENT})
                response = connection.getresponse()
                body = response.read()
            except (OSError, http.client.HTTPException):
                connection.close()
                self._local.connection = http.client.HTTPSConnection(HOST, timeout=TIMEOUT_SECONDS)
                time.sleep(backoff)
                continue
            if response.status == 429:
                retry_after = response.getheader("Retry-After", "")
                self._pacer.throttled(float(retry_after) if retry_after.isdigit() else DEFAULT_RETRY_AFTER)
                continue
            if is_block_page(response.status, body):
                raise Blocked(path)
            if response.status >= 500:
                time.sleep(backoff)
                continue
            self._pacer.succeeded()
            return Response(response.status, body)
        raise Unavailable(path)

    def get_ok(self, path: str) -> bytes:
        response = self.get(path)
        if response.status != 200:
            raise Unavailable(f"{path}: HTTP {response.status}")
        return response.body

    def _connection(self) -> http.client.HTTPSConnection:
        if not hasattr(self._local, "connection"):
            self._local.connection = http.client.HTTPSConnection(HOST, timeout=TIMEOUT_SECONDS)
        return self._local.connection
