#!/usr/bin/env python3
# -*- coding:utf-8 -*-

'''
Models for user, blog, comment.
'''

import time,uuid

from orm import Model,StringField,FloatField,BooleanField,TextField

def next_id():
    return '%015d%s000'%(int(time.time()*1000),uuid.uuid4().hex)

"""
    # 主键id的缺省值是函数next_id
    # 创建时间created_at的缺省值是函数time.time，可以自动设置当前日期和时间
    # 日期和时间用float类型存储在数据库中，而不是datetime类型---
        这么做的好处是不必关心数据库的时区以及时区转换问题，排序非常简单，显示的时候，只需要做一个float到str的转换，也非常容易
"""

class User(Model):
    __table__='users'

    id=StringField(primary_key=True,default=next_id,column_type='varchar(50)')
    email=StringField(column_type='varchar(50)')
    passwd=StringField(column_type='varchar(50)')
    admin=BooleanField()
    name=StringField(column_type='varchar(50)')
    image=StringField(column_type='varchar(500)')
    created_at=FloatField(default=time.time)

class Blog(Model):
    __table__='blogs'

    id=StringField(primary_key=True,default=next_id,column_type='varchar(50)')
    user_id=StringField(column_type='varchar(50)')
    user_name=StringField(column_type='varchar(50)')
    user_image=StringField(column_type='varchar(500)')
    name=StringField(column_type='varchar(50)')
    summary=StringField(column_type='varchar(200)')
    content=TextField()
    created_at=FloatField(default=time.time)

class Comment(Model):
    __table__='comments'

    id=StringField(primary_key=True,default=next_id,column_type='varchar(50)')
    blog_id=StringField(column_type='varchar(50)')
    user_id=StringField(column_type='varchar(50)')
    user_name=StringField(column_type='varchar(50)')
    user_image=StringField(column_type='varchar(500)')
    content=TextField()
    created_at=FloatField(default=time.time)