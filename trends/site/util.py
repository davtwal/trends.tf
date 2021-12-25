# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2021 Sean Anderson <seanga2@gmail.com>

from collections import namedtuple
from datetime import datetime, timedelta
from dateutil import tz

import flask

from ..util import clamp

def global_context(name):
    def decorator(f):
        def decorated(*args, **kwargs):
            if name not in flask.g:
                setattr(flask.g, name, f(*args, **kwargs))
            return flask.g.get(name)
        return decorated
    return decorator

@global_context('filters')
def get_filter_params():
    args = flask.request.args
    params = {}

    params['class'] = args.get('class', type=str)
    params['format'] = args.get('format', type=str)
    params['players'] = args.getlist('steamid64', type=int)

    def set_like_param(name):
        if val := args.get(name, type=str):
            params[name] = "%{}%".format(val)
        else:
            params[name] = None

    set_like_param('map')
    set_like_param('title')

    timezone = args.get('timezone', tz.UTC, tz.gettz)
    def set_date_params(name):
        name_ts = "{}_ts".format(name)
        if date := args.get(name, None, datetime.fromisoformat):
            utcdate = date.replace(tzinfo=timezone).astimezone(tz.UTC)
            params[name] = date.date().isoformat()
            params[name_ts] = utcdate.timestamp()
        else:
            params[name] = None
            params[name_ts] = None

    set_date_params('date_from')
    set_date_params('date_to')

    return params

def get_filter_clauses(params, *valid_columns, player_prefix='', log_prefix=''):
    clauses = []

    def simple_clause(name, column, prefix):
        if not params[name]:
            return

        if name in valid_columns:
            clauses.append("AND {0}{1} = %({1})s".format(prefix, name))
        elif column in valid_columns:
            clauses.append("AND {0}{1} = (SELECT {1} FROM {2} WHERE {2} = %({2})s)"
                           .format(prefix, column, name))

    simple_clause('class', 'classid', player_prefix)
    simple_clause('format', 'formatid', log_prefix)

    if 'primary_classid' in valid_columns and params['class']:
        clauses.append("""AND {}primary_classid = (
                              SELECT classid
                              FROM class
                              WHERE class = %(class)s
                          )""".format(player_prefix))

    def like_clause(name):
        if name in valid_columns and params[name]:
            clauses.append("AND {0}{1} ILIKE %({1})s".format(log_prefix, name))

    like_clause('title')
    like_clause('map')

    if 'mapid' in valid_columns and params['map']:
        clauses.append("""AND {}mapid IN (
                              SELECT mapid
                              FROM map
                              WHERE map ILIKE %(map)s
                          )""".format(log_prefix))

    def date_clause(name, op):
        if 'time' in valid_columns and params[name]:
            clauses.append("AND {}time {} %({})s::BIGINT".format(log_prefix, op, name))

    date_clause('date_from_ts', '>=')
    date_clause('date_to_ts', '<=')

    if 'logid' in valid_columns:
        for i, player in enumerate(params['players']):
            key = "player_{}".format(i)
            params[key] = player
            clauses.append("""AND {}logid IN (
                                  SELECT logid
                                  FROM player_stats
                                  WHERE steamid64 = %({})s
                           )""".format(log_prefix, key))

    return "\n".join(clauses)

dir_map = {'desc': "DESC", 'asc': "ASC"}

@global_context('order')
def get_order(column_map, default_column, default_dir='desc'):
    args = flask.request.args

    column = args.get('sort', type=str)
    if column not in column_map.keys():
        column = default_column

    dir = args.get('sort_dir', type=str)
    if dir not in dir_map.keys():
        dir = default_dir

    return ({ 'sort': column, 'sort_dir': dir },
            "{} {}".format(column_map[column], dir_map[dir]))

Page = namedtuple('Page', ('limit', 'offset'))

@global_context('page')
def get_pagination(limit=100, offset=0):
    args = flask.request.args
    limit = clamp(args.get('limit', limit, int), 0, limit)
    offset = max(args.get('offset', offset, int), 0)
    return Page(limit, offset)
