#!/usr/bin/env python3
import argparse
import os
import random
import statistics
import string
import threading
import time
from dataclasses import dataclass
from typing import Optional


def parse_args():
    parser = argparse.ArgumentParser(
        description="Stress test Camellia Redis Proxy with service prefixes, shared-auth, and hot-key simulation."
    )
    parser.add_argument("--host", default=os.environ.get("REDIS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("REDIS_PORT", "6379")))
    parser.add_argument("--password", default=os.environ.get("REDIS_PASSWORD"))
    parser.add_argument("--service", default=os.environ.get("SERVICE_NAME", "default"))
    parser.add_argument("--key-prefix", default=os.environ.get("KEY_PREFIX"))
    parser.add_argument("--clients", type=int, default=int(os.environ.get("CLIENTS", "50")))
    parser.add_argument("--requests", type=int, default=int(os.environ.get("REQUESTS", "100000")))
    parser.add_argument("--keyspace", type=int, default=int(os.environ.get("KEYSPACE", "100000")))
    parser.add_argument("--data-size", type=int, default=int(os.environ.get("DATA_SIZE", "128")))
    parser.add_argument("--set-percent", type=int, default=int(os.environ.get("SET_PERCENT", "30")))
    parser.add_argument("--get-percent", type=int, default=int(os.environ.get("GET_PERCENT", "70")))
    parser.add_argument("--hot-key-percent", type=int, default=int(os.environ.get("HOT_KEY_PERCENT", "0")))
    parser.add_argument("--hot-key-count", type=int, default=int(os.environ.get("HOT_KEY_COUNT", "1")))
    parser.add_argument("--report-every", type=int, default=int(os.environ.get("REPORT_EVERY", "2000")))
    return parser.parse_args()


def validate_args(args):
    if args.clients <= 0:
        raise ValueError("clients must be > 0")
    if args.requests <= 0:
        raise ValueError("requests must be > 0")
    if args.keyspace <= 0:
        raise ValueError("keyspace must be > 0")
    if args.data_size <= 0:
        raise ValueError("data-size must be > 0")
    if args.hot_key_count <= 0:
        raise ValueError("hot-key-count must be > 0")
    if args.set_percent < 0 or args.get_percent < 0 or args.hot_key_percent < 0:
        raise ValueError("percent values must be >= 0")
    if args.set_percent + args.get_percent != 100:
        raise ValueError("set-percent + get-percent must equal 100")
    if args.hot_key_percent > 100:
        raise ValueError("hot-key-percent must be <= 100")


def parse_moved(error_text: str) -> Optional[tuple[str, int]]:
    if "MOVED" not in error_text:
        return None
    parts = error_text.split()
    if len(parts) < 3 or ":" not in parts[2]:
        return None
    host, port = parts[2].rsplit(":", 1)
    try:
        return host, int(port)
    except ValueError:
        return None


class ProxyClient:
    def __init__(self, host: str, port: int, password: Optional[str]):
        self.redis_module = load_redis_module()
        self.response_error = self.redis_module.exceptions.ResponseError
        self.host = host
        self.port = port
        self.password = password
        self.conn = self._new_conn(host, port)

    def _new_conn(self, host: str, port: int):
        return self.redis_module.Redis(
            host=host,
            port=port,
            password=self.password,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )

    def execute(self, command: str, *args):
        try:
            return self.conn.execute_command(command, *args)
        except self.response_error as exc:
            moved = parse_moved(str(exc))
            if not moved:
                raise
            host, port = moved
            self.host = host
            self.port = port
            self.conn = self._new_conn(host, port)
            return self.conn.execute_command(command, *args)


@dataclass
class ThreadStats:
    completed: int = 0
    failures: int = 0
    set_ops: int = 0
    get_ops: int = 0
    bytes_written: int = 0
    bytes_read: int = 0
    latency_ms: list[float] = None

    def __post_init__(self):
        if self.latency_ms is None:
            self.latency_ms = []


def random_value(data_size: int) -> bytes:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=data_size)).encode()


def pick_key(prefix: str, keyspace: int, hot_key_percent: int, hot_key_count: int) -> str:
    if hot_key_percent and random.randint(1, 100) <= hot_key_percent:
        slot = random.randint(1, hot_key_count)
        return f"{prefix}:hot:{slot}"
    return f"{prefix}:key:{random.randint(1, keyspace)}"


def percentile(latencies: list[float], value: float) -> float:
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * value))))
    return ordered[index]


def worker(worker_id: int, args, requests: int, stats: ThreadStats, start_barrier: threading.Barrier):
    prefix = args.key_prefix or f"svc:{args.service}"
    client = ProxyClient(args.host, args.port, args.password)
    payload = random_value(args.data_size)

    start_barrier.wait()
    for idx in range(requests):
        key = pick_key(prefix, args.keyspace, args.hot_key_percent, args.hot_key_count)
        op = "set" if random.randint(1, 100) <= args.set_percent else "get"
        started = time.perf_counter()
        try:
            if op == "set":
                client.execute("SET", key, payload)
                stats.set_ops += 1
                stats.bytes_written += len(payload)
            else:
                value = client.execute("GET", key)
                stats.get_ops += 1
                if value is not None:
                    stats.bytes_read += len(value)
            stats.completed += 1
        except Exception:
            stats.failures += 1
        finally:
            stats.latency_ms.append((time.perf_counter() - started) * 1000)

        if args.report_every > 0 and (idx + 1) % args.report_every == 0:
            print(f"[worker-{worker_id}] progress={idx + 1}/{requests}")


def load_redis_module():
    try:
        import redis  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: python package 'redis' is required. "
            "Install with: pip install redis"
        ) from exc
    return redis


def main():
    args = parse_args()
    validate_args(args)

    requests_per_client = args.requests // args.clients
    extra_requests = args.requests % args.clients
    start_barrier = threading.Barrier(args.clients)
    threads = []
    thread_stats = []

    print(
        f"[INFO] host={args.host} port={args.port} service={args.service} "
        f"key_prefix={args.key_prefix or f'svc:{args.service}'} clients={args.clients} requests={args.requests}"
    )
    print(
        f"[INFO] ratio=set:{args.set_percent}% get:{args.get_percent}% "
        f"hot_key_percent={args.hot_key_percent}% hot_key_count={args.hot_key_count} keyspace={args.keyspace}"
    )

    suite_started = time.perf_counter()
    for worker_id in range(args.clients):
        assigned_requests = requests_per_client + (1 if worker_id < extra_requests else 0)
        stats = ThreadStats()
        thread_stats.append(stats)
        thread = threading.Thread(
            target=worker,
            args=(worker_id + 1, args, assigned_requests, stats, start_barrier),
            daemon=True,
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - suite_started

    completed = sum(item.completed for item in thread_stats)
    failures = sum(item.failures for item in thread_stats)
    set_ops = sum(item.set_ops for item in thread_stats)
    get_ops = sum(item.get_ops for item in thread_stats)
    bytes_written = sum(item.bytes_written for item in thread_stats)
    bytes_read = sum(item.bytes_read for item in thread_stats)
    latencies = [lat for item in thread_stats for lat in item.latency_ms]
    throughput = completed / elapsed if elapsed > 0 else 0.0

    print()
    print("=== Stress Test Summary ===")
    print(f"completed={completed}")
    print(f"failures={failures}")
    print(f"set_ops={set_ops}")
    print(f"get_ops={get_ops}")
    print(f"elapsed_seconds={elapsed:.2f}")
    print(f"throughput_rps={throughput:.2f}")
    print(f"latency_avg_ms={statistics.fmean(latencies):.2f}" if latencies else "latency_avg_ms=0.00")
    print(f"latency_p95_ms={percentile(latencies, 0.95):.2f}")
    print(f"latency_p99_ms={percentile(latencies, 0.99):.2f}")
    print(f"bytes_written={bytes_written}")
    print(f"bytes_read={bytes_read}")

    raise SystemExit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
