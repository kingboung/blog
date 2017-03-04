#!usr/bin/env python3
#-*- coding:utf-8 -*-
# fabric.py

import re,os
from datetime import datetime

# 导入Fabric API:
from fabric.api import *

# 服务器登录用户名
env.user='root'
# sudo用户为root:
#env.sudo_user='root'
# 服务器地址，可以有多个，依次部署:
env.hosts=['119.29.98.173']

# 服务器MySQL用户名和口令:
db_user='root'
db_password='3102693jack'

'''
每个Python函数都是一个任务
'''
_TAR_FILE='dist-awesome.tar.gz'

# 打包任务
def build():
    includes=['static','templates','transwarp','favicon.ico','*.py']
    excludes=['test','.*','*.pyc','*.pyo']
    local('rm -f dist/%s' % _TAR_FILE)
    '''
        Fabric提供:
    1、local('...')来运行本地命令;
    2、with lcd(path)可以把当前命令的目录设定为lcd()指定的目录(注意Fabric只能运行命令行命令，Windows下可能需要Cgywin环境。)
    '''
    with lcd(os.path.join(os.path.abspath('.'),'www')):
        cmd=['tar','--dereference','-czvf','../dist/%s' % _TAR_FILE]
        cmd.extend(['--exclude=\'%s\'' % ex for ex in excludes])
        cmd.extend(includes)
        local(' '.join(cmd))

_REMOTE_TMP_TAR='/tmp/%s' % _TAR_FILE
_REMOTE_BASE_DIR='/srv/awesome'

# 把打包文件上传至服务器，解压，重置www软链接，重启相关服务
def deploy():
    newdir='www-%s' % datetime.now().strftime('%y-%m-%d_%H.%M.%S')
    '''
    run()函数执行的命令是在服务器上运行
    with cd(path)和with lcd(path)类似，把当前目录在服务器端设置为cd()指定的目录
    如果一个命令需要sudo权限，就不能用run()，而是用sudo()来执行
    '''
    # 删除已有的tar文件：
    run('rm -f %s' % _REMOTE_TMP_TAR)
    # 上传新的tar文件：
    put('dist/%s' % _TAR_FILE,_REMOTE_TMP_TAR)
    # 创建新目录
    with cd(_REMOTE_BASE_DIR):
        sudo('mkdir %s' % newdir)
    # 解压到新目录:
    with cd('%s/%s' % (_REMOTE_BASE_DIR,newdir)):
        sudo('tar -xzvf %s' % _REMOTE_TMP_TAR)
    # 重置软链接:
    with cd(_REMOTE_BASE_DIR):
        sudo('rm -f www')
        sudo('ln -s %s www' % newdir)
        sudo('chown root:root www')
        sudo('chown -R root:root %s' % newdir)
    # 重启Python服务器和nginx服务器:
    with settings(warn_only=True):
        sudo('supervisorctl stop awesome')
        sudo('supervisorctl start awesome')
        sudo('/ect/init.d/nginx reload')

