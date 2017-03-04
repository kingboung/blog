#!/usr/bin/env python3
# -*- coding:utf-8 -*-

"""url handlers"""

'''
1.GET、POST方法的参数必需是KEYWORD_ONLY
2.URL参数是POSITIONAL_OR_KEYWORD
3.REQUEST参数要位于最后一个POSITIONAL_OR_KEYWORD之后的任何地方
'''

import re, time, json, logging, hashlib, base64, asyncio, markdown2

from aiohttp import web
from coroweb import get, post
from apis import Page,APIError,APIResourceNotFoundError,APIValueError,APIPermissionError

from models import User, Comment, Blog, next_id
from config import configs

COOKIE_NAME='awesession'
_COOKIE_KEY=configs.session.secret

# 检查用户是否是admin（A与B<=>非A或非B）
def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()

def get_page_index(page_str):
    p=1
    try:
        p=int(page_str)
    except ValueError as e:
        pass
    if p<1:
        p=1
    return p

def text2html(text):
    '''
    map()的两个参数一个是函数名，另一个是列表或元组。
    >>>map(lambda x:x+3, a) #这里的a同上
    >>>[3,4,5,6,7,8,9,10]

    filter（）函数包括两个参数，分别是function和list。该函数根据function参数返回的结果是否为真来过滤list参数中的项，最后返回一个新列表，如下例所示：
    >>>a=[1,2,3,4,5,6,7]
    >>>b=filter(lambda x:x>5, a)
    >>>print b
    >>>[6,7]
    '''
    lines=map(lambda s:'<p>%s</p>' % s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'),
              filter(lambda s:s.strip() != '',text.split('\n')))
    return ''.join(lines)

def user2cookie(user,max_age):
    '''
    Generate cookie str by user.
    '''
    # build cookie string by: id-expires-sha1
    expires=str(int(time.time()+max_age))
    s='%s-%s-%s-%s'%(user.id,user.passwd,expires,_COOKIE_KEY)
    L=[user.id,expires,hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

async def cookie2user(cookie_str):
    '''
    Parse cookie and load user if cookie is valid.
    '''
    if not cookie_str:
        return None
    try:
        L=cookie_str.split('-')
        # L=[uid,expires,sha1],长度必须为3
        if len(L)!=3:
            return None
        uid,expires,sha1=L
        # cookie过期
        if int(expires)<time.time():
            return None
        user=await User.find(uid)
        # 不存在该用户
        if user is None:
            return None
        s='%s-%s-%s-%s'%(uid,user.passwd,expires,_COOKIE_KEY)
        # cookie的sha1不一致
        if sha1!=hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd='******'
        return user
    except Exception as e:
        logging.exception(e)
        return None


"""————————————————————————————————————————用户浏览页面——————————————————————————————————————————"""
# 首页
@get('/')
async def index(request):
    blogs=await Blog.findAll(orderBy='created_at desc')
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }

# 管理页首页
@get('/manage/')
def manage():
    return 'redirect:/manage/comments'

# 登录页
@get('/signin')
def signin():
    return {
        '__template__':'signin.html'
    }

# 注册页
@get('/register')
def register():
    return {
        '__template__':'register.html',
    }

# 日志详情页
@get('/blog/{id}')
async def get_blog(id):
    blog=await Blog.find(id)
    comments=await Comment.findAll('blog_id=?',[id],orderBy='created_at desc')
    for c in comments:
        c.html_content=text2html(c.content)
    '''
    markdown，轻量级的标记语言，方便文章排版
    '''
    blog.html_content=markdown2.markdown(blog.content)
    return {
        '__template__':'blog.html',
        'blog':blog,
        'comments':comments
    }

# 注销页
@get('/signout')
def signout(request):
    referer=request.headers.get('Referer')
    r=web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME,'-deleted-',max_age=0,httponly=True)
    logging.info('user signed out.')
    return r


"""——————————————————————————————————————————管理页面————————————————————————————————————————————"""
# 用户列表页
@get('/manage/users')
def manage_users(*,page='1'):
    return {
        '__template__':'manage_users.html',
        'page_index':get_page_index(page)
    }

# 评论列表页
@get('/manage/comments')
def manage_comments(*,page='1'):
    return {
        '__template__':'manage_comments.html',
        'page_index':get_page_index(page)
    }

# 日志列表页
@get('/manage/blogs')
def manage_blogs(*,page='1'):
    return {
        '__template__':'manage_blogs.html',
        'page_index':get_page_index(page)
    }

# 创建日志页
@get('/manage/blogs/create')
def manage_create_blog():
    return {
        '__template__':'manage_blog_edit.html',
        'id':'',
        'action':'/api/blogs'
    }

# 修改日志页
@get('/manage/blogs/edit')
async def manage_edit_blog(*,id):
    return {
        '__template__':'manage_blog_edit.html',
        'id':id,
        'action':'/api/blogs/%s'%id
    }


"""——————————————————————————————————————————后端API————————————————————————————————————————————"""
# 获取日志
@get('/api/blogs')
async def api_blogs(*,page='1'):
    page_index=get_page_index(page)
    num=await Blog.findNumber('count(id)')
    p=Page(num,page_index)
    if num==0:
        return dict(page=p,blogs=())
    blogs=await Blog.findAll(orderBy='created_at desc',limit=(p.offset,p.limit)) # 从第offset+1个开始取limit个
    return dict(page=p,blogs=blogs)

# 创建日志
@post('/api/blogs')
async def api_create_blog(request,*,name,summary,content):
    # admin用户才能进入词条编辑页面
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name','name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary','summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content','content cannot be empty.')
    blog=Blog(user_id=request.__user__.id,user_name=request.__user__.name,user_image=request.__user__.image,name=name.strip(),summary=summary.strip(),content=content.strip())
    await blog.save()
    return blog

# 获取特定日志
@get('/api/blogs/{id}')
async def api_get_blog(*,id):
    blog=await Blog.find(id)
    return blog

# 修改日志
@post('/api/blogs/{id}')
async def api_update_blog(id,request,*,name,summary,content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name','name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary','summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content','content cannot be empty.')
    blog=await Blog.find(id)
    blog.name=name.strip()
    blog.summary=summary.strip()
    blog.content=content.strip()
    await blog.update()
    return blog

# 删除日志
@post('/api/blogs/{id}/delete')
async def api_delete_blog(request,*,id):
    check_admin(request)
    blog=await Blog.find(id)
    await blog.remove()
    return dict(id=id)

# 获取评论
@get('/api/comments')
async def api_comments(*,page='1'):
    page_index=get_page_index(page)
    num=await Comment.findNumber('count(id)')
    p=Page(num,page_index)
    if num==0:
        return dict(page=p,comments=())
    comments=await Comment.findAll(orderBy='created_at desc',limit=(p.offset,p.limit))
    return dict(page=p,comments=comments)

# 创建评论
@post('/api/blogs/{id}/comments')
async def api_comments_create(id,request,*,content):
    user=request.__user__
    if user is None:
        raise APIPermissionError('Please signin first.')
    if not content or not content.strip():
        raise APIValueError('content','content cannot be empty.')
    blog=await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment=Comment(blog_id=id,user_id=user.id,user_name=user.name,user_image=user.image,content=content.strip())
    await comment.save()
    return comment

# 删除评论
@post('/api/comments/{id}/delete')
async def api_comments_delete(id,request):
    check_admin(request)
    comment=await Comment.find(id)
    if comment is None:
        raise APIResourceNotFoundError('Comment')
    await comment.remove()
    return dict(id=id)

# 用户登录
@post('/api/authenticate')
async def authenticate(*,email,passwd):
    if not email:
        raise APIValueError('email','Invalid email.')
    if not passwd:
        raise APIValueError('passwd','Invalid password.')
    users=await User.findAll('email=?',[email])
    if len(users)==0:
        raise APIValueError('email','Email not exist.')
    user=users[0]
    # check passwd:
    sha1=hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd!=sha1.hexdigest():
        raise APIValueError('passwd','Invalid password.')
    # authenticate ok,set cookie:
    r=web.Response()
    r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
    user.passwd='******'
    r.content_type='application/json'
    r.body=json.dumps(user,ensure_ascii=False).encode('utf-8')
    return r

# 获取用户
@get('/api/users')
async def api_get_users():
    users=await User.findAll(orderBy='created_at desc')
    for u in users:
        u.passwd='******'
    return dict(users=users)

# 正则表达式匹配邮箱和密码的SHA1加密
_RE_EMAIL=re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\.\-\_]+){1,4}$')   # xxx@xx.xx.xx.xx
_RE_SHA1=re.compile((r'^[a-f0-9]{40}$'))    # 40位Hash字符串

# 用户注册
@post('/api/users')
async def api_register_user(*,email,name,passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users=await User.findAll('email=?',[email])
    if len(users)>0:
        raise APIError('register:failed','email','Email is already in use.')
    uid=next_id()
    sha1_passwd='%s:%s'%(uid,passwd)
    user=User(id=uid,name=name.strip(),email=email,passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),image='http://www.gravatar.com/avatar/%s?d=mm&s=120'%hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    # make session cookie
    r=web.Response()
    '''
    方法--set_cookie(self, name, value, *, expires=None,
                   domain=None, max_age=None, path='/',
                   secure=None, httponly=None, version=None)
    name (string) - Cookie的名称，由浏览器保存并发送至服务器。
    value (string) -Cookie的值，与Cookie的名称相对应。
    expires (int) - Cookie的过期时间，这是个可选参数，它决定cookie有效时间是多久。以秒为单位。它必须是一个整数，而绝不能是字符串。可选参数，不写该参数则默认永久有效。
    domain (string) - Cookie的有效域－在该域内cookie才是有效的。一般情况下，要在某站点内可用，该参数值该写做站点的域（比如.webpy.org），而不是站主的主机名（比如wiki.webpy.org），可选参数
    max_age(int) - 用于定义一个会话的最长持续的时间。可选参数
    path(string) - 规定 cookie 的服务器路径。可选参数
    secure (bool)- 如果为True，要求该Cookie只能通过HTTPS传输。可选参数
    '''
    r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
    user.passwd='******'
    r.content_type='application/json'
    # 因为json.dumps序列化时对中文默认使用的ascii编码.想输出真正的中文需要指定ensure_ascii=False
    r.body=json.dumps(user,ensure_ascii=False).encode('utf-8')
    return r