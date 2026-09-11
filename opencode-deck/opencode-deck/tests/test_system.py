import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from ocdeck.model import Registry
from ocdeck.common import atomic_json, read_json, identity as native_identity, alive, request
from ocdeck.broker import Broker, InstanceLock
from ocdeck.device import DeviceLoop, WheelTransport
from ocdeck.art import frame


def identity(pid=None):
    # Test-host adaptation: some isolated runners expose host /proc while
    # getpid() returns namespace PIDs. Production Windows identity is unchanged.
    if sys.platform == 'linux':
        actual = int(Path('/proc/self/stat').read_text().split()[0])
        if actual != os.getpid():
            if pid is None or pid == os.getpid():
                return native_identity(actual)
            ns = os.readlink('/proc/self/ns/pid')
            for entry in Path('/proc').iterdir():
                if not entry.name.isdigit(): continue
                try:
                    if os.readlink(entry/'ns/pid') != ns: continue
                    lines = (entry/'status').read_text().splitlines()
                    values = next(line.split()[1:] for line in lines if line.startswith('NSpid:'))
                    if int(values[-1]) == pid: return native_identity(int(entry.name))
                except (OSError, StopIteration, ValueError): pass
    return native_identity(pid)


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.now = 100
        self.dead = set()
        self.r = Registry(lambda p: p['pid'] not in self.dead, clock=lambda: self.now)

    def add(self, key='a', pid=1):
        return self.r.upsert({'id':key,'process':{'pid':pid,'created':1},'label':'Same project'})

    def state(self, key='a', status='idle', pending=0, seq=1, producer='one'):
        return self.r.snapshot(key, dict(status=status,pending=pending,seq=seq,producer=producer))

    def test_six_stable_slots_and_overflow(self):
        for n in range(7): self.add(str(n),n+1)
        self.assertEqual([self.r.records[str(n)]['slot'] for n in range(7)], [0,1,2,3,4,5,None])
        self.r.remove('2')
        self.assertEqual(self.r.records['6']['slot'],2)
        self.assertEqual(self.r.records['5']['slot'],5)

    def test_colors_and_input_priority(self):
        self.add(); self.state(status='busy'); self.assertEqual(self.r.view()[0]['state'],'running')
        self.state(status='idle',pending=2,seq=2); self.assertEqual(self.r.view()[0]['state'],'input')
        self.state(status='idle',pending=1,seq=3); self.assertEqual(self.r.view()[0]['state'],'input')
        self.state(status='idle',pending=0,seq=4); self.assertEqual(self.r.view()[0]['state'],'idle')

    def test_retry_is_running(self):
        self.add(); self.state(status='retry'); self.assertEqual(self.r.view()[0]['state'],'running')

    def test_stale_state_is_unknown_not_false_idle(self):
        self.add(); self.state(status='busy'); self.now+=11
        self.assertEqual(self.r.view()[0]['state'],'unknown')
        self.r.sweep(); self.assertEqual(len(self.r.records),1)

    def test_death_clears_even_with_fresh_heartbeat(self):
        self.add(); self.state(); self.dead.add(1); self.r.sweep()
        self.assertEqual(self.r.view()[0]['state'],'off')

    def test_sequences_and_retired_producers(self):
        self.add(); self.state(seq=10)
        self.assertFalse(self.state(status='busy',seq=9))
        self.assertTrue(self.state(seq=0,producer='two'))
        self.assertFalse(self.state(seq=99,producer='one'))

    def test_reused_slot_rejects_old_press(self):
        self.add(); old=self.r.view()[0]; self.r.remove('a'); self.add('b',2)
        self.assertIsNone(self.r.resolve(old['slot'],old['generation'],old['id']))

    def test_repeated_registration_is_idempotent(self):
        self.add(); self.add(); self.assertEqual(len(self.r.records),1)

    def test_process_identity_cannot_be_replaced(self):
        self.add()
        with self.assertRaises(ValueError): self.add(pid=2)

    def test_invalid_snapshot_rejected(self):
        self.add()
        with self.assertRaises(ValueError): self.state(status='pretend')
        with self.assertRaises(ValueError): self.state(pending=-1)

    def test_concurrent_registration(self):
        threads=[threading.Thread(target=self.add,args=(str(n),n+1)) for n in range(6)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(set(self.r.slots)),6)


class ArtTests(unittest.TestCase):
    def test_all_empty_pixels_are_black(self):
        self.assertIsNone(frame('off','',0,0).getbbox())

    def test_every_active_state_animates(self):
        for state in ['running','input','idle','ready','unknown']:
            self.assertNotEqual(frame(state,'Project',0,0).tobytes(),frame(state,'Project',0,6).tobytes())

    def test_native_mini_image_encoding_and_packetization(self):
        from StreamDeck.Devices.StreamDeckMini import StreamDeckMini
        from StreamDeck.ImageHelpers import PILHelper
        class Fake:
            def __init__(self): self.writes=[]
            def write(self,data): self.writes.append(data); return len(data)
            def close(self): pass
            def read(self,n): return None
        transport=Fake(); deck=StreamDeckMini(transport)
        image=PILHelper.to_native_key_format(deck, frame('input','Test',0,0))
        self.assertTrue(image.startswith(b'BM'))
        deck.set_key_image(0,image)
        self.assertGreater(len(transport.writes),1)
        self.assertTrue(all(len(x)==1024 for x in transport.writes))

    def test_press_callback_only_uses_down_and_rendered_generation(self):
        r=Registry(lambda p:True); q=queue.Queue(); stop=threading.Event()
        d=DeviceLoop(r,q,stop,{},True)
        d.presented[0]={'id':'old','slot':0,'generation':3}
        d.press(0,False); self.assertTrue(q.empty())
        d.press(0,True); self.assertEqual(q.get()['generation'],3)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.identity_patch=patch('ocdeck.broker.identity',identity);self.identity_patch.start()
        self.focused=[]
        self.b=Broker(self.root,mock=True,focus=lambda r:self.focused.append(r['id']) or {'ok':True})
        self.thread=threading.Thread(target=self.b.serve); self.thread.start()
        for _ in range(100):
            if (self.root/'discovery.json').exists(): break
            time.sleep(.01)

    def tearDown(self):
        self.b.stop.set(); self.thread.join(5); self.identity_patch.stop(); self.tmp.cleanup()

    def api(self, method, path, body=None): return request(method,path,body,root=self.root)

    def test_auth_and_origin_rejected(self):
        port=read_json(self.root/'discovery.json')['port']
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/status')
        self.assertEqual(cm.exception.code,401)
        req=urllib.request.Request(f'http://127.0.0.1:{port}/v1/status',headers={'Origin':'https://example.com'})
        with self.assertRaises(urllib.error.HTTPError) as cm: urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code,403)

    def test_actual_http_register_update_focus_delete(self):
        self.api('POST','/v1/register',{'id':'live','process':identity(),'label':'Test'})
        self.api('PUT','/v1/instances/live',{'seq':1,'producer':'p','status':'busy','pending':0})
        before=self.api('GET','/v1/status')['slots'][0]
        self.assertEqual(before['state'],'running')
        self.api('POST','/v1/focus',before)
        self.assertEqual(self.focused,['live'])
        self.assertEqual(before,self.api('GET','/v1/status')['slots'][0])
        self.api('DELETE','/v1/instances/live')
        self.assertEqual(self.api('GET','/v1/status')['slots'][0]['state'],'off')

    def test_dead_real_process_removed(self):
        child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
        try:
            self.api('POST','/v1/register',{'id':'child','process':identity(child.pid)})
            child.terminate(); child.wait()
            for _ in range(30):
                if self.api('GET','/v1/status')['slots'][0]['state']=='off': break
                time.sleep(.1)
            self.assertEqual(self.api('GET','/v1/status')['slots'][0]['state'],'off')
        finally:
            if child.poll() is None: child.kill(); child.wait()

    def test_pid_reuse_wrong_creation_time_is_rejected(self):
        p=identity();p['created']-=100
        with self.assertRaises(urllib.error.HTTPError): self.api('POST','/v1/register',{'id':'bad','process':p})

    def test_ready_only_in_device_frame_and_relinquishes_slot(self):
        for _ in range(20):
            if self.b.device.presented[0]: break
            time.sleep(.05)
        self.assertEqual(self.b.device.presented[0]['state'],'ready')
        self.api('POST','/v1/register',{'id':'a','process':identity()})
        time.sleep(.2)
        self.assertEqual(self.b.device.presented[0]['id'],'a')

    def test_blank_press_does_not_focus(self):
        result=self.api('POST','/v1/focus',self.api('GET','/v1/status')['slots'][1])
        self.assertFalse(result['ok']);self.assertEqual(self.focused,[])

    def test_node_bridge_round_trip_and_broker_recovery(self):
        # Real JavaScript bridge, real HTTP broker, injected OpenCode-shaped facts.
        env=dict(os.environ,OCDECK_HOME=str(self.root),TEST_PROCESS=json.dumps(identity()))
        script=Path(__file__).with_name('bridge-integration.mjs')
        result=subprocess.run(['node',str(script)],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class LockTests(unittest.TestCase):
    def test_singleton_lock(self):
        with tempfile.TemporaryDirectory() as td:
            with InstanceLock(Path(td)):
                with self.assertRaises(OSError):
                    with InstanceLock(Path(td)): pass


if __name__=='__main__': unittest.main()
