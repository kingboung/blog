#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import os,sys,time,subprocess

"""
    watchdog用来监控指定目录/文件的变化，如添加删除文件或目录、修改文件内容、重命名文件或目录等，每种变化都会产生一个事件，
且有一个特定的事件类与之对应，然后再通过事件处理类来处理对应的事件，怎么样处理事件完全可以自定义，只需继承事件处理类的基类并重写
对应实例方法。
"""

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

def log(s):
    print('[Monitor] %s'%s)

class MyFileSystemEventHandler(FileSystemEventHandler):

    def __init__(self,fn):
        super(MyFileSystemEventHandler,self).__init__()
        self.restart=fn

    # 利用watchdog接收文件变化的通知，如果是.py文件，就自动重启wsgiapp.py进程
    def on_any_event(self,event):
        if event.src_path.endswith('.py'):
            log('Python source file changed: %s'%event.src_path)
            self.restart()

command=['echo','ok']
process=None

# 杀死进程
def kill_process():
    global process
    if process:
        log('Kill process [%s]...'%process.pid)
        process.kill()
        process.wait()
        log('Process ended with code %s.'%process.returncode)

# 打开新进程
def start_process():
    global process,command
    log('Start process %s...'%' '.join(command))
    #利用Python自带的subprocess实现进程的启动和终止，并把输入输出重定向到当前进程的输入输出中(command为‘python3 文件名’)
    process=subprocess.Popen(command,stdin=sys.stdin,stdout=sys.stdout,stderr=sys.stderr)

# 重启进程
def restart_process():
    kill_process()
    start_process()

def start_watch(path,callback):
    observer=Observer()
    observer.schedule(MyFileSystemEventHandler(restart_process),path,recursive=True)
    observer.start()
    log('Watching directory %s...'%path)
    start_process()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__=='__main__':
    argv=sys.argv[1:]
    if not argv:
        print('Usage: ./pymonitor your-script.py')
        exit(0)
    if argv[0]!='python3':
        argv.insert(0,'python3')
    command=argv
    path=os.path.abspath('.')
    start_watch(path,None)