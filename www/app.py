#!/usr/bin/env python3
#-*- coding:utf-8 -*-

'''
async web application.
'''

import logging; logging.basicConfig(level=logging.INFO)

import asyncio,os,json,time
from datetime import datetime

from aiohttp import web
from jinja2 import Environment,FileSystemLoader

import orm
from config import configs
from coroweb import add_routes,add_static

from handlers import cookie2user,COOKIE_NAME

"""初始化jinja2"""
def init_jinja2(app,**kw):
    logging.info('init jinja2...')
    options=dict(
        autoescape=kw.get('autoescape',True),
        block_start_string=kw.get('block_start_string','{%'),
        block_end_string=kw.get('block_end_string','%}'),
        variable_start_string=kw.get('variable_start_string','{{'),
        variable_end_string=kw.get('variable_end_string','}}'),
        auto_reload=kw.get('auto_reload',True)
    )
    path=kw.get('path',None)
    if path is None:
        path=os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates')
    logging.info('set jinja2 template path: %s'%path)
    env=Environment(loader=FileSystemLoader(path),**options)
    filters=kw.get('filters',None)
    if filters is not None:
       for name,f in filters.items():
           env.filters[name]=f
    app['__templating__']=env


"""
                                         middleware是一种拦截器

    一个URL在被某个函数处理前，可以经过一系列的middleware的处理。一个middleware可以改变URL的输入、输出，甚至可以决定不继续处理而直接返回。
middleware的用处就在于把通用的功能从每个URL处理函数中拿出来，集中放到一个地方。

    记录URL日志的logger_factory;
    response_factory把返回值转换为web.Response对象再返回，以保证满足aiohttp的要求;
    data_factory把POST上来的信息处理成可以应用的格式。
"""

"""记录URL日志"""
async def logger_factory(app,handler):
    async def logger(request):
        # 记录日志
        logging.info('Request: %s %s'%(request.method,request.path))
        # 继续处理请求
        return (await handler(request))
    return logger

"""利用middle在处理URL之前，把cookie解析出来，并将登录用户绑定到request对象上，这样，后续的URL处理函数就可以直接拿到登录用户"""
async def auth_factory(app,handler):
    async def auth(request):
        logging.info('check user: %s %s'%(request.method,request.path))
        request.__user__=None
        cookie_str=request.cookies.get(COOKIE_NAME)
        if cookie_str:
            user=await cookie2user(cookie_str)
            if user:
                logging.info('set current user: %s'%user.email)
                request.__user__=user
        # '/manage/'的url需有管理员权限才能访问
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
            return web.HTTPFound('/signin')
        return (await handler(request))
    return auth

"""POST请求日志记录和处理,主要作用就是把这些参数统一绑定在request.__data__上"""
async def data_factory(app,handler):
    async def parse_data(request):
        if request.method=='POST':
            if request.content_type.startswith('application/json'):
                request.__data__=await request.json()
                logging.info('request json: %s'%str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__=await request.post()
                logging.info('request form: %s'%str(request.__data__))
        return (await handler(request))
    return parse_data

"""GET请求日志记录和处理"""
async def response_factory(app,handler):
    async def response(request):
        logging.info('Response handler...')
        # 结果:
        r=await handler(request)
        if isinstance(r,web.StreamResponse):
            return r
        if isinstance(r,bytes):
            resp=web.Response(body=r)
            resp.content_type='application/octet-stream'
            return resp
        if isinstance(r,str):
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:]) #'redirect:xxxxx'=>xxxxx  r[9:]
            resp=web.Response(body=r.encode('utf-8'))
            resp.content_type='text/html;charset=utf-8'
            return resp
        if isinstance(r,dict):
            template=r.get('__template__')
            if template is None:
                resp=web.Response(body=json.dumps(r,ensure_ascii=False,default=lambda o:o.__dict__).encode('utf-8'))
                resp.content_type='application/json;charset=utf-8'
                return resp
            else:
                r['__user__']=request.__user__
                resp=web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type='text/html;charset=utf-8'
                return resp
        if isinstance(r,int) and r>=100 and r<600:
            return web.Response(r)
        if isinstance(r,tuple) and len(r)==2:
            t,m=r
            if isinstance(t,int) and t>=100 and t<600:
                return web.Response(t,str(m))
        # default:
        resp=web.Response(body=str(r).encode('utf-8'))
        resp.content_type='text/plain;charset=utf-8'
        return resp
    return response

def datetime_filter(t):
    delta=int(time.time()-t)
    '''
    以u或U开头的字符串表示unicode字符串
    Unicode是书写国际文本的标准方法。如果你想要用非英语写文本,那么你需要有一个支持Unicode的编辑器。
    类似地,Python允许你处理Unicode文本——你只需要在字符串前加上前缀u或U。
    '''
    if delta<60:
        return u'1分钟前'
    if delta<3600:
        return u'%s分钟前'%(delta//60)
    if delta<86400:
        return u'%s小时前'%(delta//3600)
    if delta<604800:
        return u'%s天前'%(delta//86400)
    dt=datetime.fromtimestamp(t)
    return u'%s年%s月%s日'%(dt.year,dt.month,dt.day)

async def init(loop):
    await orm.create_pool(loop=loop,**configs.db)
    app=web.Application(loop=loop,middlewares={
        logger_factory,auth_factory,response_factory
    })
    init_jinja2(app,filters=dict(datetime=datetime_filter))
    add_routes(app,'handlers')
    add_static(app)
    srv=await loop.create_server(app.make_handler(),'127.0.0.1',9000)
    logging.info('server started at http://127.0.0.1:9000...')
    return srv


loop=asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()