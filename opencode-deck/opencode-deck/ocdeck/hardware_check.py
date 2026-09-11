"""Manual six-key diagnostic with actual USB events, isolated from the broker."""
import json
import queue
import time
from PIL import Image, ImageDraw, ImageFont
from .broker import InstanceLock
from .common import home, read_json, atomic_json
from .device import enumerate_minis, WheelTransport


def run():
    from StreamDeck.Devices.StreamDeckMini import StreamDeckMini
    from StreamDeck.ImageHelpers import PILHelper
    root = home(); root.mkdir(parents=True, exist_ok=True)
    with InstanceLock(root):
        devices = enumerate_minis()
        serial = read_json(root / 'config.json', {}).get('serial')
        if serial: devices = [d for d in devices if d.get('serial_number') == serial]
        if len(devices) != 1: raise RuntimeError('Expected one Mini; select a serial in config.json')
        deck = StreamDeckMini(WheelTransport(devices[0]))
        presses = queue.Queue()
        observed = []
        try:
            deck.open(); deck.set_brightness(45)
            for key in range(6):
                im = Image.new('RGB', (80, 80), '#123b5c')
                ImageDraw.Draw(im).text((40, 40), str(key+1), font=ImageFont.load_default(size=36), fill='white', anchor='mm')
                deck.set_key_image(key, PILHelper.to_native_key_format(deck, im))
            deck.set_key_callback(lambda d, k, pressed: presses.put(k+1) if pressed else None)
            print('Six numbered images submitted. Confirm the physical display is 1 2 3 / 4 5 6.')
            print('Press physical keys 1 through 6 in order within 30 seconds.')
            deadline = time.monotonic()+30
            while len(observed)<6 and time.monotonic()<deadline:
                try:
                    key=presses.get(timeout=min(1,max(.01,deadline-time.monotonic())))
                    observed.append(key);print(f'Physical key-down received: {key}',flush=True)
                except queue.Empty: pass
            result={'time':time.time(),'serial':devices[0].get('serial_number'),
                    'physicalKeys':observed,'keyOrderPass':observed==[1,2,3,4,5,6],
                    'displayVisuallyConfirmed':False,
                    'note':'Display appearance requires human confirmation; API writes are not camera evidence.'}
            atomic_json(root/'hardware-check.json',result)
            print(json.dumps(result,indent=2))
        finally:
            try:
                blank=PILHelper.to_native_key_format(deck,Image.new('RGB',(80,80),'black'))
                for key in range(6):deck.set_key_image(key,blank)
            finally:deck.close()
