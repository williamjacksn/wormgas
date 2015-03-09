import asyncio
import collections
import datetime
import json
import sys


class EventEmitter(object):
    def __init__(self):
        self._events = collections.defaultdict(list)

    def on(self, event, func=None):
        def _on(f):
            self._events[event].append(f)
            return f
        if func is None:
            return _on
        return _on(func)

    def emit(self, event, *args, **kwargs):
        handled = False
        for f in self._events[event]:
            f(*args, **kwargs)
            handled = True
        if not handled:
            for f in self._events['catch_all']:
                f(*args, **kwargs)
        return handled


class Config:
    def __init__(self, path, pretty=False):
        self.data = dict()
        self.path = path
        self.pretty = pretty
        if self.path.exists():
            with self.path.open() as f:
                self.data = json.load(f)

    def __contains__(self, item):
        return item in self.data

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self._flush()

    def _flush(self):
        with self.path.open('w') as f:
            if self.pretty:
                json.dump(self.data, f, indent=4, sort_keys=True)
            else:
                json.dump(self.data, f)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def keys(self):
        return self.data.keys()

    def remove(self, key):
        if key in self.data:
            del self.data[key]
            self._flush()

    def set(self, key, value):
        self[key] = value


class IRCClient(asyncio.Protocol):
    def __init__(self, config_path):
        self.buf = b''
        self.ee = EventEmitter()
        self.c = Config(config_path)
        self.loop = asyncio.get_event_loop()
        self.t = None
        self.debug = False
        self.admins = set()
        self.members = set()
        self.in_channel = False
        self.topic = None

    def __call__(self):
        return self

    @staticmethod
    def log(message):
        t = datetime.datetime.utcnow()
        print('{} {}'.format(t, message))
        sys.stdout.flush()

    @staticmethod
    def is_irc_channel(s):
        return s and s.startswith('#')

    @staticmethod
    def remove_format_codes(m):
        m = m.replace(b'\x02', b'')  # bold
        m = m.replace(b'\x0f', b'')  # normal
        m = m.replace(b'\x16', b'')  # italic/reversed
        m = m.replace(b'\x1f', b'')  # underline
        while 3 in m:  # color
            idx = m.find(3)
            mark = idx + 1
            if m[mark:mark + 2].isdigit():
                mark += 2
            elif m[mark:mark + 1].isdigit():
                mark += 1
            if len(m) > mark and m[mark] == 44:  # b','
                if m[mark + 1:mark + 3].isdigit():
                    mark += 3
                elif m[mark + 1:mark + 2].isdigit():
                    mark += 2
            m = m.replace(m[idx:mark], b'')
        return m

    def smart_decode(self, m):
        m = self.remove_format_codes(m)
        try:
            return m.decode()
        except UnicodeDecodeError:
            self.log('** Failed decode using utf-8, trying next encoding.')
        try:
            return m.decode('iso-8859-1')
        except:
            self.log('** Failed decode using iso-8859-1.')
            self.log(repr(m))
            raise

    @staticmethod
    def parse_hostmask(hostmask):
        # 'nick!user@host' => ('nick', 'user', 'host')
        nick, _, userhost = hostmask.partition('!')
        user, _, host = userhost.partition('@')
        return nick, user, host

    def add_admin(self, nick):
        if self.debug:
            self.log('** Added {} to admins list'.format(nick))
        self.admins.add(nick)
        self.members.add(nick)

    def remove_admin(self, nick):
        if self.debug:
            self.log('** Removed {} from admins list'.format(nick))
        self.admins.discard(nick)

    def add_member(self, nick):
        if self.debug:
            self.log('** Added {} to members list'.format(nick))
        self.members.add(nick)

    def remove_member(self, nick):
        if self.debug:
            self.log('** Removed {} from members list'.format(nick))
        self.members.discard(nick)
        self.admins.discard(nick)

    def connection_made(self, transport):
        self.t = transport
        if self.debug:
            self.log('** Connection made')
        self.out('NICK {}'.format(self.c['irc:nick']))
        m = 'USER {} {} x :{}'
        ident = self.c['irc:ident']
        self.out(m.format(ident, self.c['irc:host'], self.c['irc:name']))

    def data_received(self, data):
        self.buf = self.buf + data
        lines = self.buf.split(b'\n')
        self.buf = lines.pop()
        for line in lines:
            line = line.strip()
            self.loop.call_soon(self._in, line)

    def connection_lost(self, exc):
        if self.debug:
            self.log('** Connection lost')
        self.loop.stop()

    def _in(self, message):
        # convert message from bytes to unicode
        # then emit an appropriate event
        message = self.smart_decode(message)
        if self.debug:
            self.log('<= {}'.format(message))
        tokens = message.split()
        if len(tokens) > 0 and tokens[0] == 'PING':
            self.out('PONG {}'.format(tokens[1]))
            self.ee.emit(tokens[0], message, self)
        elif len(tokens) > 3 and tokens[3] == ':\x01ACTION':
            self.ee.emit('ACTION', message, self)
        elif len(tokens) > 1:
            if tokens[1] == '353':
                self._handle_namreply(tokens)
            elif tokens[1] == '366':
                self.in_channel = True
            elif tokens[1] == 'JOIN':
                self._handle_join(tokens)
            elif tokens[1] == 'MODE':
                self._handle_mode(tokens)
            elif tokens[1] == 'NICK':
                self._handle_nick(tokens)
            elif tokens[1] == 'PART':
                self._handle_part(tokens)
            elif tokens[1] == 'QUIT':
                self._handle_quit(tokens)
            elif tokens[1] == 'TOPIC' or tokens[1] == '332':
                self._handle_topic(message)
            self.ee.emit(tokens[1], message, self)
        else:
            self.ee.emit('catch_all', message, self)

    def out(self, message):
        # log messages then convert from unicode to bytes
        # and write to transport
        if message:
            if self.debug:
                self.log('=> {}'.format(message))
            self.t.write('{}\r\n'.format(message).encode())

    def send_action(self, target, message):
        self.out('PRIVMSG {} :\x01ACTION {}\x01'.format(target, message))

    def send_privmsg(self, target, message):
        self.out('PRIVMSG {} :{}'.format(target, message))

    def send_topic(self, topic):
        self.out('TOPIC {} :{}'.format(self.c['irc:channel'], topic))

    def _handle_join(self, tokens):
        source = tokens[0].lstrip(':')
        nick, _, _ = self.parse_hostmask(source)
        self.add_member(nick)

    def _handle_mode(self, tokens):
        target = tokens[2]
        if target == self.c.get('irc:channel'):
            modes = list()
            modespec = tokens[3]
            mode_action = ''
            for char in modespec:
                if char in ['+', '-']:
                    mode_action = char
                else:
                    modes.append('{}{}'.format(mode_action, char))
            for mode, nick in zip(modes, tokens[4:]):
                if mode in ['+h', '+o']:
                    self.add_admin(nick)
                elif mode in ['-h', '-o']:
                    self.remove_admin(nick)

    def _handle_namreply(self, tokens):
        for name in tokens[5:]:
            name = name.lstrip(':')
            nick = name.lstrip('~@%+')
            self.add_member(nick)
            if name.startswith(('~', '@', '%')):
                self.add_admin(nick)

    def _handle_nick(self, tokens):
        source = tokens[0].lstrip(':')
        nick, _, _ = self.parse_hostmask(source)
        new_nick = tokens[2].lstrip(':')
        if nick in self.admins:
            self.add_admin(new_nick)
        else:
            self.add_member(new_nick)
        self.remove_member(nick)

    def _handle_part(self, tokens):
        source = tokens[0].lstrip(':')
        nick, _, _ = self.parse_hostmask(source)
        self.remove_member(nick)

    def _handle_quit(self, tokens):
        source = tokens[0].lstrip(':')
        nick, _, _ = self.parse_hostmask(source)
        self.remove_member(nick)

    def _handle_topic(self, message):
        new_topic = message.split(' :', 1)[1]
        self.topic = new_topic
        self.log('** Setting new topic {!r}'.format(new_topic))
