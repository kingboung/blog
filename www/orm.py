#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import logging

import aiomysql

"""将使用到的SQL语句记录到日志中"""
def log(sql,args=()):
    logging.info('SQL:%s' % sql)

"""创建连接池"""
async def create_pool(loop,**kw):
    logging.info('create database connection pool...')
    global __pool   #全局变量__pool用于存储整个连接池
    __pool=await aiomysql.create_pool(
        host=kw.get('host','localhost'),
        port=kw.get('port',3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset','utf8'),
        autocommit=kw.get('autocommit',True),
        # 默认最大连接数为10
        maxsize=kw.get('maxsize',10),
        minsize=kw.get('minsize',1),

        # 接受一个event_loop的实例
        loop=loop
    )

"""SELECT语句封装(参数化，防止SQL注入)"""
async def select(sql,args,size=None):
    log(sql,args)
    global __pool
    async with __pool.get() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # SQL语句的占位符是？，而MySQL的占位符是%s，实现内部的替换
            await cur.execute(sql.replace('?','%s'),args or ())
            if size:
                # 指定数量的记录
                rs=await cur.fetchmany(size)
            else:
                # 所有的记录
                rs=await cur.fetchall()
        #await cur.close()
        logging.info('rows returned:%s' %len(rs))
        #conn.close()
        # 返回结果集
        return rs

"""INSERT、UPDATE、DELETE语句封装"""
async def execute(sql,args,autocommit=True):
    log(sql)
    async with __pool.get() as conn:
        if not autocommit:
            await conn.begin()
        # 如果没有自动提交事务就报错
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?','%s'),args)
                affected=cur.rowcount
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise
        #finally:
        #    conn.close()
        # 返回结果数
        return affected

"""根据输入的参数生成占位符列表"""
def create_args_string(num):
    L=[]
    for n in range(num):
        L.append('?')
    return ', '.join(L)

"""元类（将具体的子类，如User的映射信息读取出来）"""
class ModelMetaclass(type):
    # __new__控制__init__的执行，所以在其执行之前执行
    # cls:代表要__init__的类，此参数在实例化时由Python解释器自动提供(例如下文的User和Model)
    # bases：代表继承父类的集合
    # attrs：类的方法集合
    def __new__(cls,name,bases,attrs):
        # 排除Model类本身
        if name=='Model':
            return type.__new__(cls,name,bases,attrs)
        # 获取table名称
        tableName=attrs.get('__table__',None) or name
        logging.info('found model: %s (table: %s)'%(name,tableName))
        # 获取所有的Field和主键名
        mappings=dict()
        fields=[]
        primaryKey=None
        for k,v in attrs.items():
            if isinstance(v,Field):
                logging.info('  found mapping: %s ==> %s'%(k,v))
                mappings[k]=v
                if v.primary_key:
                    # 找到主键
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field: %s'%k)
                    primaryKey=k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found.')
        for k in mappings.keys():
            attrs.pop(k)
        # 除主键外的属性名为``（运算字符串）列表形式
        escaped_fields=list(map(lambda f:'`%s`'%f,fields))
        attrs['__mappings__']=mappings      # 保存属性和列的映射关系
        attrs['__table__']=tableName        # 保存列表名
        attrs['__primary_key__']=primaryKey # 主键属性名
        attrs['__fields__']=fields          # 除主键外的属性名
        # 构造默认的SELECT,INSERT,UPDATE和DELETE语句：
        attrs['__select__']='select `%s`, %s from `%s`'\
                            %(primaryKey,', '.join(escaped_fields),tableName)
        attrs['__insert__']='insert into `%s` (%s,`%s`) values(%s)'\
                            %(tableName,', '.join(escaped_fields),primaryKey,create_args_string(len(escaped_fields)+1))
        attrs['__update__']='update `%s` set %s where `%s`=?'\
                            %(tableName,', '.join(map(lambda f:'`%s`=?'%(mappings.get(f).name or f),fields)),primaryKey)
        attrs['__delete__']='delete from `%s` where `%s`=?'\
                            %(tableName,primaryKey)
        return type.__new__(cls,name,bases,attrs)

"""ORM映射的基类"""
# Model类的任意子类可以映射一个数据库表
# Model类可以看作是对所有数据库表操作的基本定义的映射

# 基于字典查询形式
# Model从dict继承，拥有字典的所有功能，同时实现特殊方法__getattr__和__setattr__，能够实现属性操作
# 实现数据库操作的所有方法，定义为class方法，所有继承自Model都具有数据库操作方法
class Model(dict,metaclass=ModelMetaclass):
    def __init__(self,**kw):
        super(Model,self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" %key)

    def __setattr__(self, key, value):
        self[key]=value

    def getValue(self,key):
        return getattr(self,key,None)

    def getValueOrDefault(self,key):
        value=getattr(self,key,None)
        if value is None:
            field=self.__mappings__[key]
            if field.default is not None:
                # 如果field.default是函数，value=field.default()；如果是值，则value=field.default
                value=field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' %(key,str(value)))
                setattr(self,key,value)
        return value

    @classmethod
    async def find(cls,primarykey):
        '''find object by primary key.'''
        rs=await select('%s where `%s`=?'%(cls.__select__,cls.__primary_key__),[primarykey],1)
        if len(rs)==0:
            return None
        return cls(**rs[0])

    @classmethod
    async def findNumber(cls,selectField,where=None,args=None):
        '''find number by select and where.'''
        sql=['select %s _num_ from `%s`'%(selectField,cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs=await select(' '.join(sql),args,1)
        if len(rs)==0:
            return None
        return rs[0]['_num_']

    @classmethod
    async def findAll(cls,where=None,args=None,**kw):
        '''find object by where clause.'''
        sql=[cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args=[]
        orderBy=kw.get('orderBy',None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit=kw.get('limit',None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit,int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit,tuple) and len(limit)==2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s'%str(limit))
        rs=await select(' '.join(sql),args)
        return [cls(**r) for r in rs]

    async def save(self):
        args=list(map(self.getValueOrDefault,self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows=await execute(self.__insert__,args)
        if rows!=1:
            logging.warn('failed to insert record:affected row: %s'%rows)

    async def update(self):
        args=list(map(self.getValue,self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows=await execute(self.__update__,args)
        if rows!=1:
            logging.warn('failed to update by primary key:affected rows: %s'%rows)

    async def remove(self):
        args=[self.getValue(self.__primary_key__)]
        rows=await execute(self.__delete__,args)
        if rows!=1:
            logging.warn('failed to remove by primary key:affected rows: %s'%rows)

"""定义Field类，负责保存(数据库)表的字段名和字段类型"""
class Field(object):
    # 表的字段包含名字、类型、是否为表的主键和默认值
    def __init__(self,name,column_type,primary_key,default):
        self.name=name
        self.column_type=column_type
        self.primary_key=primary_key
        self.default=default

    def __str__(self):
        return '<%s, %s:%s>'%(self.__class__.__name__,self.column_type,self.name)

"""
    定义不同类型的衍生Field
    表的不同列的字段的类型不一样
"""

class StringField(Field):
    def __init__(self,name=None,primary_key=False,default=None,column_type='varchar(100)'):
        super().__init__(name,column_type,primary_key,default)

class BooleanField(Field):
    def __init__(self,name=None,default=False):
        super().__init__(name,'boolean',False,default)

class IntegerField(Field):
    def __init__(self,name=None,primary_key=False,default=0):
        super().__init__(name,'bigint',primary_key,default)

class FloatField(Field):
    def __init__(self,name=None,primary_key=False,default=0.0):
        super().__init__(name,'real',primary_key,default)

class TextField(Field):
    def __init__(self,name=None,primary_key=False,default=None):
        super().__init__(name,'text',primary_key,default)