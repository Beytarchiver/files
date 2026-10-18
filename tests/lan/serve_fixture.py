"""Loopback-only interoperability fixture. Never used by the desktop application."""
import argparse
import json
import os
from pathlib import Path
from queue import Empty, Queue
import signal
import sys
import tempfile
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from lan_transfer.server import TransferServer


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ready-file',type=Path,required=True)
    parser.add_argument('--size',type=int,default=131079)
    args=parser.parse_args()
    if not 0<=args.size<=10*1024*1024: parser.error('Fixture size must be at most 10 MiB')
    stopped=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_:stopped.set())
    events=Queue()
    server=TransferServer(events)
    with tempfile.TemporaryDirectory(prefix='beyt-interop-') as temporary:
        source=Path(temporary)/'interop.bin'
        source.write_bytes(bytes((i%251 for i in range(args.size))))
        try:
            qr=server.start('127.0.0.1')
            fd=os.open(args.ready_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w',encoding='utf-8') as stream: json.dump(qr,stream)
            while not stopped.is_set():
                try: event=events.get(timeout=.1)
                except Empty:continue
                if event['kind']=='pair_requested':
                    server.approve(event['request_id'])
                    server.offer(source)
        finally:
            server.stop()
            args.ready_file.unlink(missing_ok=True)


if __name__=='__main__':main()
