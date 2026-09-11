"""Optional actual OpenCode server/plugin test with a local deterministic model.
No cloud model, credentials, or physical Stream Deck required.
Set OPENCODE_TEST_BIN to an installed opencode executable. Run from bundle root.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))
from test_system import identity
from unittest.mock import patch
from ocdeck.broker import Broker
from ocdeck.common import atomic_json, request

binary=os.environ.get('OPENCODE_TEST_BIN')
if not binary: raise SystemExit('Set OPENCODE_TEST_BIN first; this is an optional live integration test.')

class Model(BaseHTTPRequestHandler):
    counter=0
    def log_message(self,*args): pass
    def do_POST(self):
        value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        messages=value.get('messages',[])
        text=json.dumps(messages)
        # First response calls a real OpenCode tool; subsequent response ends turn.
        tool='question' if 'question-case' in text else 'bash'
        had_result=any(m.get('role')=='tool' for m in messages)
        if had_result:
            delta={'content':'Fixture completed.'}; reason='stop'
        else:
            arguments=({'questions':[{'question':'Choose a test option','header':'Deck test','options':[{'label':'Continue','description':'Complete the deterministic fixture'}]}]}
                       if tool=='question' else {'command':'echo DECK_TEST','description':'Harmless Stream Deck fixture'})
            delta={'tool_calls':[{'index':0,'id':'fixture-call','type':'function','function':{'name':tool,'arguments':json.dumps(arguments)}}]};reason='tool_calls'
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
        for d,finish in [({'role':'assistant'},None),(delta,None),({},reason)]:
            chunk={'id':'chatcmpl-fixture','object':'chat.completion.chunk','created':int(time.time()),'model':'fixture',
                   'choices':[{'index':0,'delta':d,'finish_reason':finish}]}
            self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
        self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()

with tempfile.TemporaryDirectory() as td:
    root=Path(td);config=root/'config';config.mkdir();(config/'plugins').mkdir()
    plugin=Path(__file__).resolve().parents[1]/'plugins/server.mjs'
    (config/'plugins/deck.js').write_text('export { DeckBridge } from '+json.dumps(plugin.as_uri())+';\n')
    model=ThreadingHTTPServer(('127.0.0.1',0),Model)
    threading.Thread(target=model.serve_forever,daemon=True).start()
    atomic_json(config/'opencode.json',{'$schema':'https://opencode.ai/config.json',
      'model':'fixture/fixture','small_model':'fixture/fixture','permission':{'bash':'ask'},
      'provider':{'fixture':{'npm':'@ai-sdk/openai-compatible','name':'Local fixture',
         'options':{'baseURL':f'http://127.0.0.1:{model.server_address[1]}/v1','apiKey':'fixture'},
         'models':{'fixture':{'name':'Fixture','limit':{'context':8192,'output':1024}}}}}})
    binding=root/'binding.json';atomic_json(binding,{'id':'live-runtime','process':identity(),'label':'OpenCode live','managed':True})
    broker=Broker(root,mock=True)
    with patch('ocdeck.broker.identity',identity):
        thread=threading.Thread(target=broker.serve);thread.start()
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        env=dict(os.environ,OCDECK_HOME=str(root),OCDECK_BINDING=str(binding),OPENCODE_CONFIG_DIR=str(config),
                 OPENCODE_DISABLE_DEFAULT_PLUGINS='true',OPENCODE_DISABLE_AUTOUPDATE='true',
                 OPENCODE_DISABLE_MODELS_FETCH='true',OPENCODE_DISABLE_LSP_DOWNLOAD='true',
                 OPENCODE_DISABLE_CLAUDE_CODE='true',OPENCODE_DISABLE_EXTERNAL_SKILLS='true')
        log=open(root/'opencode.log','w+')
        process=subprocess.Popen([binary,'serve','--hostname','127.0.0.1','--port',str(port)],env=env,cwd=root,stdout=log,stderr=log)
        def api(method,path,data=None):
            req=Request(f'http://127.0.0.1:{port}{path}',method=method,
              data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=4) as r:
                raw=r.read();return json.loads(raw) if raw else None
        def wait(check,label,seconds=30):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                try:
                    result=check()
                    if result:return result
                except Exception: pass
                time.sleep(.1)
            raise AssertionError('Timed out: '+label)
        def color():return request('GET','/v1/status',root=root)['slots'][0]['state']
        try:
            wait(lambda:api('GET','/global/health'),'OpenCode startup')
            print('Actual OpenCode server started',flush=True)
            for case,route,reply in [('permission-case','permission',{'reply':'once'}),('question-case','question',{'answers':[['Continue']]})]:
                session=api('POST','/session',{})
                api('POST',f"/session/{session['id']}/prompt_async",{'parts':[{'type':'text','text':case}]})
                pending=wait(lambda:api('GET','/'+route),'actual '+route+' tool request')
                wait(lambda:color()=='input','physical-display model becomes red')
                print(case+': real request and RED state PASS',flush=True)
                api('POST',f"/{route}/{pending[0]['id']}/reply",reply)
                wait(lambda:color()=='idle','idle after reply')
                print(case+': reply, real tool completion, AMBER state PASS',flush=True)
            print('LIVE OPENCODE PLUGIN INTEGRATION PASS',flush=True)
        except Exception:
            log.flush();log.seek(0);print(log.read()[-10000:])
            print('Broker slots:',broker.registry.view())
            raise
        finally:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            broker.stop.set();thread.join(5);model.shutdown();model.server_close();log.close()
