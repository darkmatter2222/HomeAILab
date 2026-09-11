"""Serialized registry. Color is a projection; button presses never mutate it."""
import copy
import threading
import time
import uuid


class Registry:
    def __init__(self, probe, clock=time.monotonic, stale_after=10):
        self.probe, self.clock, self.stale_after = probe, clock, stale_after
        self.lock = threading.RLock()
        self.records = {}
        self.slots = [None] * 6
        self.generations = [0] * 6
        self.epoch = str(uuid.uuid4())

    def upsert(self, data):
        key = data.get("id", "")
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ValueError("id must be 1..128 characters")
        with self.lock:
            record = self.records.get(key)
            if record is None:
                process = data.get("process")
                if not isinstance(process, dict) or self.probe(process) is not True:
                    raise ValueError("process identity is not live on this host")
                slot = next((i for i, value in enumerate(self.slots) if value is None), None)
                if slot is not None:
                    self.generations[slot] += 1
                    self.slots[slot] = key
                record = {"id": key, "process": process, "slot": slot,
                          "label": str(data.get("label", "OpenCode"))[:100],
                          "windowToken": str(data.get("windowToken", ""))[:128],
                          "seq": -1, "producer": None, "retired": [],
                          "status": "unknown", "pending": 0,
                          "lastState": 0, "lastSeen": self.clock(), "detail": "Connecting"}
                self.records[key] = record
            elif data.get("process") != record["process"]:
                raise ValueError("instance process identity cannot change")
            record["lastSeen"] = self.clock()
            return copy.deepcopy(record)

    def snapshot(self, key, data):
        status = data.get("status")
        if status not in ("idle", "busy", "retry", "unknown"):
            raise ValueError("invalid status")
        seq, producer = data.get("seq"), data.get("producer")
        if not isinstance(seq, int) or seq < 0 or not isinstance(producer, str) or not producer or len(producer) > 128:
            raise ValueError("invalid sequence/producer")
        pending = data.get("pending", 0)
        if type(pending) is not int or not 0 <= pending <= 10000:
            raise ValueError("invalid pending count")
        with self.lock:
            r = self.records[key]
            if producer in r["retired"]:
                return False
            if r["producer"] != producer:
                if r["producer"]:
                    r["retired"].append(r["producer"])
                r["producer"], r["seq"] = producer, -1
            if seq <= r["seq"]:
                return False
            r.update(seq=seq, status=status, pending=pending,
                     detail=str(data.get("detail", ""))[:200],
                     lastState=self.clock(), lastSeen=self.clock())
            return True

    def remove(self, key):
        with self.lock:
            r = self.records.pop(key, None)
            if r and r["slot"] is not None:
                slot = r["slot"]
                self.slots[slot] = None
                self.generations[slot] += 1
            # Overflow agents take a freed slot in registration order.
            for candidate in self.records.values():
                if candidate["slot"] is None and None in self.slots:
                    slot = self.slots.index(None)
                    self.generations[slot] += 1
                    self.slots[slot], candidate["slot"] = candidate["id"], slot

    def sweep(self):
        with self.lock:
            for key, record in list(self.records.items()):
                if self.probe(record["process"]) is False:
                    self.remove(key)

    def view(self):
        with self.lock:
            result = []
            for slot, key in enumerate(self.slots):
                r = self.records.get(key)
                state = "off"
                if r:
                    if self.clock() - r["lastState"] > self.stale_after or r["status"] == "unknown":
                        state = "unknown"
                    elif r["pending"]:
                        state = "input"
                    elif r["status"] in ("busy", "retry"):
                        state = "running"
                    else:
                        state = "idle"
                result.append({"slot": slot, "generation": self.generations[slot],
                               "id": key, "state": state, "label": r["label"] if r else "",
                               "detail": r["detail"] if r else ""})
            return result

    def resolve(self, slot, generation, key):
        with self.lock:
            if type(slot) is not int or not 0 <= slot < 6:
                return None
            if self.slots[slot] != key or self.generations[slot] != generation:
                return None
            r = self.records.get(key)
            if not r or self.probe(r["process"]) is not True:
                return None
            return copy.deepcopy(r)
