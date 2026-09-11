import argparse
import json
from pathlib import Path
import sys
from .common import home, identity, request


def main():
    parser = argparse.ArgumentParser(prog='ocdeck')
    sub = parser.add_subparsers(dest='command', required=True)
    broker = sub.add_parser('broker'); broker.add_argument('--mock', action='store_true')
    sub.add_parser('status'); sub.add_parser('stop'); sub.add_parser('devices')
    sub.add_parser('hardware-check')
    launch = sub.add_parser('launch'); launch.add_argument('args', nargs=argparse.REMAINDER)
    route = sub.add_parser('route'); route.add_argument('args', nargs=argparse.REMAINDER)
    worker = sub.add_parser('worker'); worker.add_argument('spec')
    ident = sub.add_parser('identity'); ident.add_argument('pid', type=int)
    plug = sub.add_parser('install-plugin'); plug.add_argument('--mode', choices=['server', 'tui'], default='server'); plug.add_argument('--config-dir')
    preview = sub.add_parser('preview'); preview.add_argument('--output', default='animation-preview.gif')
    focus = sub.add_parser('focus'); focus.add_argument('slot', type=int)
    args = parser.parse_args()
    try:
        if args.command == 'broker':
            from .broker import run
            run(mock=args.mock)
        elif args.command in ('status', 'stop'):
            print(json.dumps(request('GET' if args.command == 'status' else 'POST', '/v1/' + args.command), indent=2))
        elif args.command == 'identity': print(json.dumps(identity(args.pid)))
        elif args.command == 'launch':
            from .launcher import launch
            launch(args.args[1:] if args.args[:1] == ['--'] else args.args)
        elif args.command == 'route':
            from .launcher import route
            return route(args.args[1:] if args.args[:1] == ['--'] else args.args)
        elif args.command == 'worker':
            from .launcher import worker
            return worker(args.spec)
        elif args.command == 'install-plugin':
            from .launcher import install_plugin
            install_plugin(args.mode, args.config_dir)
        elif args.command == 'devices':
            from .device import enumerate_minis
            print(json.dumps([{k: (v.decode(errors='replace') if isinstance(v, bytes) else v)
                               for k, v in d.items()} for d in enumerate_minis()], indent=2))
        elif args.command == 'hardware-check':
            from .hardware_check import run
            run()
        elif args.command == 'focus':
            if not 1 <= args.slot <= 6: raise ValueError('Slot must be 1..6')
            view = request('GET', '/v1/status')['slots'][args.slot - 1]
            print(json.dumps(request('POST', '/v1/focus', view), indent=2))
        elif args.command == 'preview':
            from .art import frame
            from PIL import Image, ImageDraw
            images = []
            states = ['running', 'idle', 'input', 'ready', 'unknown', 'off']
            for phase in range(24):
                im = Image.new('RGB', (532, 370), '#10141d')
                d = ImageDraw.Draw(im)
                d.text((22, 12), 'OPENCODE / STREAM DECK MINI', fill='white')
                for k, state in enumerate(states):
                    im.paste(frame(state, 'HomeAILab', k, phase, 150), (22 + (k % 3)*170, 40 + (k // 3)*160))
                images.append(im)
            images[0].save(args.output, save_all=True, append_images=images[1:], duration=83, loop=0)
            print(str(Path(args.output).resolve()))
    except Exception as error:
        print(f'ocdeck: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
