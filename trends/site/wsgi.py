# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2020-21 Sean Anderson <seanga2@gmail.com>

import base64
from decimal import Decimal
import gettext
import hashlib
import os, os.path

import flask
import werkzeug.exceptions
import werkzeug.routing
import werkzeug.utils

from .api import api, json_handler
from .player import player
from .root import root
from .util import put_db

try:
    import pkg_resources
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    try:
        version = pkg_resources.require("trends.tf")[0].version
    except pkg_resources.DistributionNotFound:
        version = None

    sentry_sdk.init(
        release=version,
        integrations=[FlaskIntegration()],
        traces_sample_rate=1
    )

    def trace_template_start(app, template, context):
        span = sentry_sdk.Hub.current.start_span(op='render', description=template.name)
        context['span'] = span
        span.__enter__()

    def trace_template_finish(app, template, context):
        context['span'].__exit__(None, None, None)

    flask.before_render_template.connect(trace_template_start)
    flask.template_rendered.connect(trace_template_finish)
except ImportError:
    pass

class DefaultConfig:
    DATABASE = "postgresql:///trends"
    TIMEOUT = 60000

class EnvConfig:
    def __init__(self):
        for name in ("DATABASE", "TIMEOUT"):
            val = os.environ.get(name)
            if val is not None:
                setattr(self, name, val)

def json_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError("Object of type '{}' is not JSON serializable" \
                    .format(type(obj).__name__))

def duration_filter(timestamp):
    mm, ss = divmod(timestamp, 60)
    hh, mm = divmod(mm, 60)
    if hh:
        return "{:.0f}:{:02.0f}:{:02.0f}".format(hh, mm, ss)
    else:
        return "{:.0f}:{:02.0f}".format(mm, ss)

def avatar_filter(hash, size='full'):
    if not hash:
        return ''
    url = "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/{}/{}{}.jpg"
    return url.format(hash[:2], hash, {
            'small': '',
            'medium': '_medium',
            'full': '_full',
        }[size])

def anynone(iterable):
    for item in iterable:
        if item is None:
            return False
    return True

class StaticHashDefaults:
    def __init__(self, app):
        self.app = app
        self.cache = {}

    def __call__(self, endpoint, values):
        if endpoint != 'static' or 'filename' not in values:
            return

        filename = werkzeug.utils.safe_join(self.app.static_folder, values['filename'])
        if not os.path.isfile(filename):
            return

        mtime, hash = self.cache.get(filename, (None, None))
        if mtime == os.path.getmtime(filename):
            values['h'] = hash
            return

        hash = hashlib.md5()
        with open(filename, 'rb') as file:
            hash.update(file.read())
        hash = base64.urlsafe_b64encode(hash.digest())[:10]

        self.cache[filename] = (mtime, hash)
        values['h'] = hash

class IntListConverter(werkzeug.routing.BaseConverter):
    def to_python(self, value):
        try:
            return [int(val) for val in value.split('+')]
        except ValueError:
            return []

    def to_url(self, values):
        try:
            return '+'.join(str(value) for value in values)
        # flask turns (foo) into bare foo, so handle this special case
        except TypeError:
            return str(values)

def html_handler(error):
    if flask.request.path.startswith('/api/'):
        return json_handler(error)
    return flask.render_template("error.html", error=error), error.code

def create_app():
    app = flask.Flask(__name__)
    app.config.from_object(DefaultConfig)
    app.config.from_object(EnvConfig())

    app.teardown_appcontext(put_db)
    app.url_defaults(StaticHashDefaults(app))
    app.url_map.converters['intlist'] = IntListConverter

    app.add_template_filter(any)
    app.add_template_filter(all)
    app.add_template_filter(anynone)
    app.add_template_filter(duration_filter, 'duration')
    app.add_template_filter(avatar_filter, 'avatar')

    app.jinja_options['trim_blocks'] = True
    app.jinja_options['lstrip_blocks'] = True
    app.jinja_env.policies["json.dumps_kwargs"] = { 'default': json_default }
    app.jinja_env.globals.update(zip=zip)
    app.jinja_env.add_extension('jinja2.ext.do')
    app.jinja_env.add_extension('jinja2.ext.i18n')
    app.jinja_env.install_null_translations(newstyle=True)

    app.register_error_handler(werkzeug.exceptions.HTTPException, html_handler)
    app.register_blueprint(root)
    app.register_blueprint(player, url_prefix='/player/<int:steamid>')
    app.register_blueprint(api, url_prefix='/api/v1')

    return app
