#usr/bin/env python3
# -*- coding:utf-8 -*-

import functools,logging,asyncio,inspect,os
from urllib import parse
from aiohttp import web
from apis import APIError

"""定义@get()"""
def get(path):
    '''
    Define decorator @get('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kw):
            return func(*args,**kw)
        wrapper.__method__='GET'
        wrapper.__route__=path
        return wrapper
    return decorator

"""定义@post()"""
def post(path):
    '''
    Define decorator @post('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kw):
            return func(*args,**kw)
        wrapper.__method__='POST'
        wrapper.__route__=path
        return wrapper
    return decorator


def get_required_kw_args(fn):
    args=[]
    '''
    ***对于方法def fun(arg1,arg2=default): ... ***
    >>>inspect.signature(fun)
    <Signature (arg1,arg2=default)>
    >>>inspect.signature(fun).parameters
    mappingproxy(OrderedDict([('arg1',<Parameter "arg1">),('arg2',<Parameter "arg2=default">)]))
    >>>for name,param in (inspect.signature(fun).parameters):
    ...    print(name,param)
    ...
    arg1 arg1
    arg2 arg2=default
    '''
    params=inspect.signature(fn).parameters
    for name,param in params.items():
        '''
        ***对于方法def fun(a,b=default1,*c,d=default2,e,**f): ... ***
        a.kind为POSITIONAL_OR_KEYWORD,a.default为empty
        b.kind为POSITIONAL_OR_KEYWORD,b.default为default1
        c.kind为VAR_POSITIONAL,c.default为empty
        d.kind为KEYWORD_ONLY,d.default为default2
        e.kind为KEYWORD_ONLY,e.default为empty
        f.kind为VAR_KEYWORD,f.default为empty
        '''
        if param.kind==inspect.Parameter.KEYWORD_ONLY and param.default==inspect.Parameter.empty:
            args.append(name)
    return tuple(args)

def get_name_kw_args(fn):
    args=[]
    params=inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind==inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)

def has_named_kw_args(fn):
    params=inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind==inspect.Parameter.KEYWORD_ONLY:
            return True

def has_var_kw_args(fn):
    params=inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind==inspect.Parameter.VAR_KEYWORD:
            return True

def has_request_arg(fn):
    sig=inspect.signature(fn)
    params=sig.parameters
    found=False
    for name,param in params.items():
        if name=='request':
            found=True
            continue
        if found and (param.kind!=inspect.Parameter.VAR_KEYWORD and
                param.kind!=inspect.Parameter.KEYWORD_ONLY and param.kind!=inspect.Parameter.VAR_POSITIONAL):
            raise ValueError('Request parameter must be the last named parameter in function: %s%s'%(fn.__name__,str(sig)))
    return found

"""
    1.从URL函数中分析其需要接收的参数
    2.从request中获取必要的参数
    3.调用URL函数
    4.把结果转换为web.Response对象
"""
class RequestHandler(object):
    def __init__(self,app,fn):
        self.app=app
        self._func=fn
        self._has_request_arg=has_request_arg(fn)
        self._has_var_kw_arg=has_var_kw_args(fn)
        self._has_named_kw_args=has_named_kw_args(fn)
        self._named_kw_args=get_name_kw_args(fn)
        self._required_kw_args=get_required_kw_args(fn)

    async def __call__(self,request):
        kw=None
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            # POST方法
            if request.method=='POST':
                '''
                text/html ： HTML格式
                text/plain ：纯文本格式
                text/xml ：  XML格式
                image/gif ：gif图片格式
                image/jpeg ：jpg图片格式
                image/png：png图片格式

                application/xhtml+xml ：XHTML格式
                application/xml     ： XML数据格式
                application/atom+xml  ：Atom XML聚合格式
                application/json    ： JSON数据格式
                application/pdf       ：pd
                application/msword  ： f格式Word文档格式
                application/octet-stream ： 二进制流数据（如常见的文件下载）
                application/x-www-form-urlencoded ： <form encType=””>中默认的encType，form表单数据被编码为key/value格式发送到服务器（表单默认的提交数据的格式）

                multipart/form-data ： 需要在表单中进行文件上传时，就需要使用该格式
                '''

                # 没有消息主体
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content-Type.')

                ct=request.content_type.lower()

                # 消息主体是序列化的json字符串
                if ct.startswith('application/json'):
                    params=await request.json()
                    # 用json方法读取出来的信息不是dict
                    if not isinstance(params,dict):
                        return web.HTTPBadRequest('JSON body must be object.')
                    # 用json方法读取出来的信息是dict
                    kw=params

                # 消息主体是表单
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params=await request.post()
                    '''
                    dictMerge=dict(dict1, **dict2)
                    将dict1和dict2合并成dictMerge，若dict1为空，该函数作用相当于dictMerge=dict2
                    '''
                    kw=dict(**params)

                # 消息是主体不是以上两种
                else:
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)


            # GET方法
            if request.method=='GET':
                # 存在查询字符串
                qs=request.query_string
                if qs:
                    kw=dict()
                    '''
                    parse.parse_qs功能块演示
                    >>> url="http://localhost/test.py?a=hello&b=world "
                    >>> result=urlparse.urlparse(url)
                    >>> result
                    ParseResult(scheme='http', netloc='localhost', path='/test.py', params='', query='a=hello&b=world ', fragment='')
                    >>> urlparse.parse_qs(result.query,True)
                    {'a': ['hello'], 'b': ['world ']}
                    >>> params=urlparse.parse_qs(result.query,True)
                    >>> params
                    {'a': ['hello'], 'b': ['world ']}
                    >>> params['a'],params['b']
                    (['hello'], ['world '])
                    '''
                    for k,v in parse.parse_qs(qs,True).items():
                        kw[k]=v[0]


        # kw为空，添加match_info的信息
        if kw is None:
            kw=dict(**request.match_info)

        #  kw不为空
        else:
            # fn有关键字参数而没有可变关键字参数
            if not self._has_var_kw_arg and self._named_kw_args:
                # remove all unamed kw:
                copy=dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name]=kw[name]
                kw=copy
            # check named arg:
            for k,v in request.match_info.items():
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args: %s'%k)
                kw[k]=v

        # fn中有request参数
        if self._has_request_arg:
            kw['request']=request
        # check required arg:
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest('Missing argument: %s'%name)
        logging.info('call with args: %s'%str(kw))
        '''
        kw的参数到底要去哪里去获取呢？
        1.request.match_info的参数：match_info主要是保存像@get('/blog/{id}')里面的id，就是路由路径里的参数
        2.GET的参数：像例如/?page=2
        3.POST的参数：api的json或者是网页中form
        4.request参数：有时需要验证用户信息就需要获取request里面的数据
        '''
        try:
            r=await self._func(**kw)    # 将每个参数的值提取出来并且传参到该方法，最后调用该方法
            return r
        except APIError as e:
            return dict(error=e.error,data=e.data,message=e.message)


def add_static(app):
    path=os.path.join(os.path.dirname(os.path.abspath(__file__)),'static')
    r'''
    os.path.abspath(__file__)                   ==>F:\Code\Python3.5Code\test\test.py
    os.path.dirname(__file__)                   ==>F:/Code/Python3.5Code/test
    os.path.dirname(os.path.abspath(__file__))  ==>F:\Code\Python3.5Code\test
    '''
    app.router.add_static('/static/',path)
    logging.info('add static %s => %s'%('/static/',path))


"""用来注册一个URL处理函数"""
def add_route(app,fn):
    method=getattr(fn,'__method__',None)
    path=getattr(fn,'__route__',None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.'%str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn=asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)'
                 %(method,path,fn.__name__,', '.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method,path,RequestHandler(app,fn))


"""把很多次add_route()注册的调用变成自动扫描,把module_name模块的所有符合条件的函数注册了"""
def add_routes(app,module_name):
    n=module_name.rfind('.')    #module_name,如coroweb.add_routes或者coroweb
    '''
    __import__(name, globals=None, locals=None, fromlist=(), level=0)       # 可选参数默认为globals(),locals(),[]

    作用：
        同import语句同样的功能，但__import__是一个函数，并且只接收字符串作为参数，所以它的作用就可想而知了。
    其实import语句就是调用这个函数进行导入工作的，import sys <==>sys = __import__(‘sys‘)

    说明：
        通常在动态加载时可以使用到这个函数，比如你希望加载某个文件夹下的所用模块，但是其下的模块名称又会经常变化时，
    就可以使用这个函数动态加载所有模块了，最常见的场景就是插件功能的支持。

    eg:
    __import__(‘os‘)
    __import__(‘os‘,globals(),locals(),[‘path‘,‘pip‘])  #等价于from os import path, pip
    '''
    '''
    locals()和globals()

    说明：
        这两个函数主要提供，基于字典的访问局部和全局变量的方式。
    '''
    if n==(-1):
        mod=__import__(module_name,globals(),locals())  #<module 'xxxx' from 'x:\\xx\\xx\\x.py'>
    else:
        name=module_name[n+1:]
        mod=getattr(__import__(module_name[:n],globals(),locals(),[name]),name) #<function xx at xxxxxxxxx>
    for attr in dir(mod):
        # 去除以'_'开头的方法
        if attr.startswith('_'):
            continue
        fn=getattr(mod,attr)
        if callable(fn):
            method=getattr(fn,'__method__',None)
            path=getattr(fn,'__route__',None)
            if method and path:
                add_route(app,fn)