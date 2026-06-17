"""
Tor IP Rotator — Multi-port SOCKS5 proxy with stem NEWNYM circuit rotation.
5 parallel SocksPorts = 5 independent exit IPs simultaneously.
NEWNYM signal = force new circuit on rate limit.

Usage:
    from tor_rotator import TorRotator
    tor = TorRotator()
    client = tor.get_client(port_idx=0)  # Get client on specific port
    r = client.get("https://api.openalex.org/works?search=test")
    if r.status_code == 429:
        tor.rotate()  # NEWNYM - force new IP
    tor.close()
"""
import httpx
import random
import threading
import time
from stem import Signal
from stem.control import Controller


# Tor SOCKS ports configured in /etc/tor/torrc
TOR_PORTS = [9050, 9052, 9054, 9056, 9058]
TOR_CONTROL_PORT = 9051
TOR_PASSWORD = "paper2026"

# NEWNYM cooldown (Tor enforces min ~5s between signals)
NEWNYM_COOLDOWN = 8


class TorRotator:
    """Thread-safe Tor multi-port SOCKS5 rotator with NEWNYM circuit control."""
    
    def __init__(self, password: str = TOR_PASSWORD):
        self._lock = threading.Lock()
        self._controller = None
        self._last_newnym = 0
        self._password = password
        self._port_idx = 0
        self._connect_controller()
    
    def _connect_controller(self):
        """Connect to Tor control port for NEWNYM signals."""
        try:
            self._controller = Controller.from_port(port=TOR_CONTROL_PORT)
            self._controller.authenticate(password=self._password)
        except Exception as e:
            print(f"[tor_rotator] Control port auth failed: {e}, using SOCKS only")
            self._controller = None
    
    def rotate(self, force: bool = False) -> bool:
        """Send NEWNYM signal to rotate all circuits. Returns True if signal sent."""
        if not self._controller:
            return False
        
        with self._lock:
            now = time.time()
            wait = self._controller.get_newnym_wait()
            if not force and now - self._last_newnym < NEWNYM_COOLDOWN:
                remaining = NEWNYM_COOLDOWN - (now - self._last_newnym)
                return False
            
            try:
                self._controller.signal(Signal.NEWNYM)
                self._last_newnym = time.time()
                return True
            except Exception as e:
                print(f"[tor_rotator] NEWNYM failed: {e}")
                return False
    
    def get_port(self) -> int:
        """Get next port (round-robin). Each port = independent circuit."""
        with self._lock:
            port = TOR_PORTS[self._port_idx % len(TOR_PORTS)]
            self._port_idx += 1
            return port
    
    def get_random_port(self) -> int:
        """Get random port for IP diversity."""
        return random.choice(TOR_PORTS)
    
    def get_client(self, port: int = None, timeout: float = 20.0) -> httpx.Client:
        """Get httpx client routed through Tor SOCKS5.
        
        Args:
            port: Specific Tor port (None = round-robin)
            timeout: Request timeout in seconds
        
        Returns:
            httpx.Client configured with SOCKS5 proxy
        """
        if port is None:
            port = self.get_port()
        
        proxy_url = f"socks5h://127.0.0.1:{port}"
        return httpx.Client(proxy=proxy_url, timeout=timeout)
    
    def get_ip(self, port: int = None) -> str:
        """Get current exit IP for a port."""
        if port is None:
            port = self.get_port()
        try:
            client = self.get_client(port=port, timeout=10.0)
            r = client.get("https://api.ipify.org")
            client.close()
            return r.text.strip()
        except Exception as _e:
            print(f"[tor_rotator] get_ip failed for port {port}: {_e}")
            return "?"
    
    def test_connection(self, url: str = "https://api.openalex.org/works?search=test&per_page=1") -> bool:
        """Test if Tor connection works for academic API."""
        try:
            client = self.get_client(timeout=15.0)
            r = client.get(url)
            client.close()
            return r.status_code == 200
        except Exception as _e:
            print(f"[tor_rotator] test_connection failed: {_e}")
            return False
    
    def close(self):
        """Close Tor controller connection."""
        if self._controller:
            try:
                self._controller.close()
            except Exception as _e:
                print(f"[tor_rotator] controller.close failed: {_e}")


# Global singleton
_tor = None
_tor_lock = threading.Lock()


def get_tor() -> TorRotator:
    """Get global TorRotator singleton."""
    global _tor
    with _tor_lock:
        if _tor is None:
            _tor = TorRotator()
        return _tor


def get_tor_client(timeout: float = 20.0) -> tuple[httpx.Client, int]:
    """Get httpx client with Tor proxy. Returns (client, port)."""
    tor = get_tor()
    port = tor.get_port()
    return tor.get_client(port=port, timeout=timeout), port


def rotate_ip() -> bool:
    """Force IP rotation via NEWNYM. Returns True if signal sent."""
    tor = get_tor()
    return tor.rotate()


if __name__ == "__main__":
    print("🧅 Tor IP Rotator Test")
    tor = TorRotator()
    
    # Test 1: Get IPs from different ports
    print("\n📡 Testing 5 ports (each = different exit IP):")
    ips = []
    for port in TOR_PORTS:
        ip = tor.get_ip(port)
        ips.append(ip)
        print(f"  Port {port}: {ip}")
    
    unique = len(set(ips))
    print(f"  → {unique} unique IPs across {len(TOR_PORTS)} ports")
    
    # Test 2: OpenAlex through Tor
    print("\n🔬 Testing OpenAlex through Tor:")
    client = tor.get_client(timeout=15.0)
    try:
        r = client.get("https://api.openalex.org/works?search=machine+learning&per_page=1&mailto=test@example.com")
        print(f"  HTTP {r.status_code} | Content: {len(r.content)} bytes")
    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        client.close()
    
    # Test 3: NEWNYM rotation
    print("\n🔄 Testing NEWNYM rotation:")
    old_ip = tor.get_ip(TOR_PORTS[0])
    print(f"  Before: {old_ip}")
    if tor.rotate():
        time.sleep(3)
        new_ip = tor.get_ip(TOR_PORTS[0])
        print(f"  After:  {new_ip}")
        print(f"  → IP changed: {old_ip != new_ip}")
    else:
        print("  NEWNYM signal failed")
    
    tor.close()
    print("\n✅ Done")
