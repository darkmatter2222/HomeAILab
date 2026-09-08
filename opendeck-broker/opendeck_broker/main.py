"""Broker entrypoint: wire config + device + focus + observer + adapter + loop.

Run at user logon in the interactive session (not a Session-0 service), with
restart-on-failure supervision (research sections 4, 8).
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Optional

from .api import ApiServer
from .broker import Broker
from .config import Config
from .device.hid_mini import ElgatoMiniHID
from .device.mock import MockDevice
from .focus.windows import WindowsFocusAdapter
from .lock import BrokerLock
from .opencode.adapter import OpenCodeAdapter
from .opencode.observe import DbObserver
from .registry import Registry


@dataclass
class Stack:
    config: Config
    broker: Broker
    adapter: OpenCodeAdapter
    device: object
    api: Optional[ApiServer]


def build_stack(config: Optional[Config] = None, use_mock: bool = False) -> Stack:
    config = config or Config.from_env()
    registry = Registry()
    observer = DbObserver(config.db())
    adapter = OpenCodeAdapter(registry, observer)

    if use_mock:
        device = MockDevice()
    else:
        device = ElgatoMiniHID(serial=config.device_serial)

    focus = WindowsFocusAdapter()
    broker = Broker(registry=registry, device=device, focus=focus, image_size=config.image_size)
    api = ApiServer(broker, adapter, config)
    return Stack(config=config, broker=broker, adapter=adapter, device=device, api=api)


def run(config: Optional[Config] = None, use_mock: bool = False, tick: Optional[float] = None, max_ticks: Optional[int] = None) -> int:
    config = config or Config.from_env()
    stack = build_stack(config=config, use_mock=use_mock)
    if tick is None:
        tick = config.tick_seconds
    lock = BrokerLock()
    if not lock.acquire():
        print("another opendeck-broker is already running; exiting")
        return 0
    try:
        if not stack.broker.start():
            print("failed to open the Stream Deck Mini (is it attached + disabled in Elgato?)")
            return 2
        port = stack.api.start()
        print(f"opendeck-broker on http://{stack.config.host}:{port}  device={stack.device.name}")
        ticks = 0
        while True:
            stack.adapter.refresh()
            stack.broker.render()
            stack.broker.process_presses()
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                break
            time.sleep(tick)
        return 0
    finally:
        stack.api.stop()
        stack.broker.stop()
        lock.release()


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="opendeck-broker")
    p.add_argument("--mock", action="store_true", help="use an in-memory device (no physical Mini)")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--once", action="store_true", help="run a single tick then exit (smoke test)")
    args = p.parse_args(argv)

    config = Config.from_env()
    if args.port is not None:
        config.port = args.port
    return run(config=config, use_mock=args.mock, max_ticks=1 if args.once else None)


if __name__ == "__main__":
    raise SystemExit(main())
