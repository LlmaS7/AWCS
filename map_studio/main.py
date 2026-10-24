"""Run the independent map generator/manager with the Python standard library."""
import argparse
from pathlib import Path
import sys
from threading import Event
import webbrowser

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from map_studio.manager import start_server


def main():
    parser = argparse.ArgumentParser(description='AWCS 地图工坊：生成、预览、管理和导出')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--no-browser',action='store_true')
    args = parser.parse_args()
    server,url = start_server(args.port)
    print('AWCS Map Studio: '+url,flush=True)
    if not args.no_browser: webbrowser.open(url)
    try: Event().wait()
    except KeyboardInterrupt: pass
    finally: server.shutdown();server.server_close()


if __name__=='__main__': main()
