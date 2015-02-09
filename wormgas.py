#!/usr/bin/env python
'''
wormgas -- IRC bot for Rainwave (http://rainwave.cc)
https://github.com/williamjacksn/wormgas
'''

import cobe.brain
import datetime
import dbaccess
import importlib
import inspect
import irc.bot
import os
import random
import re
import requests
import subprocess
import sys
import time
import urlparse
import util
import xml.etree.ElementTree


def log(message):
    t = datetime.datetime.utcnow()
    print(u'{} {}'.format(t, message))

_abspath = os.path.abspath(__file__)
_commands = set()
_plug_commands = dict()
_plug_commands_admin = dict()

PRIVMSG = u'__privmsg__'


def command_handler(command):
    '''Decorate a method to register as a command handler for provided
    regex.'''
    def decorator(func):
        # Compile the command into a regex.
        regex = re.compile(command, re.I)

        def wrapped(self, nick, msg, channel):
            '''Command with stored regex that will execute if it matches
            msg.'''
            # If the regex does not match the message, return False.
            result = regex.search(msg)
            if not result:
                return False

            # The msg matches pattern for this command, so run it.
            func(self, nick, channel, **result.groupdict())
            return True
        # Add the wrapped function to a set, so we can iterate over them later.
        _commands.add(wrapped)

        # Return the original, undecorated method. It can still be called
        # directly without worrying about regexes. This also allows registering
        # one method as a handler for multiple input regexes.
        return func
    return decorator


class Wormgas(irc.bot.SingleServerIRCBot):

    channel_ids = {
        u'rw': 1,
        u'game': 1,
        u'oc': 2,
        u'ocr': 2,
        u'vw': 3,
        u'mw': 3,
        u'cover': 3,
        u'covers': 3,
        u'bw': 4,
        u'chip': 4,
        u'ch': 4,
        u'ow': 5,
        u'omni': 5,
        u'all': 5
    }

    def __init__(self):
        self.path, self.file = os.path.split(_abspath)
        self.brain = cobe.brain.Brain(u'{}/brain.sqlite'.format(self.path))

        config_json = u'{}/config.json'.format(self.path)
        rps_json = u'{}/rps.json'.format(self.path)
        keys_json = u'{}/keys.json'.format(self.path)
        self.config = dbaccess.Config(config_json, rps_json, keys_json)

        # Load plugins
        for plug_name in self.config.get(u'plugins', list())[:]:
            public, private = self.handle_load([u'!load', plug_name])
            for m in private:
                log(m)

        self.mb = util.CollectionOfNamedLists(u'{}/mb.json'.format(self.path))
        self.tf = util.TitleFetcher()

        args = sys.argv[1:]
        for arg in args:
            if arg.startswith(u'--set-'):
                key, value = arg[6:].split(u'=', 1)
                print u'Setting \'{}\' to \'{}\'.'.format(key, value)
                self.config.set(key, value)

        # Set up ignore if the ignore list is non-empty.
        ignore = self.config.get(u'msg:ignore', u'')
        self.reignore = None
        if ignore:
            self.reignore = re.compile(ignore, re.IGNORECASE)

        server = self.config.get(u'irc:server')
        nick = self.config.get(u'irc:nick')
        name = self.config.get(u'irc:name')
        super(Wormgas, self).__init__([(server, 6667)], nick, name)
        self.connection.buffer_class.errors = u'replace'

    def stop(self):
        '''Save all data and shut down the bot.'''
        del self.config
        del self.brain

    def _dispatcher(self, c, e):
        et = e.type
        if et not in self._events_not_logged():
            s = e.source
            t = e.target
            log(u'{}, {}, {} -- {}'.format(et, s, t, e.arguments))
        irc.bot.SingleServerIRCBot._dispatcher(self, c, e)

    def _aux_wa(self, query):
        '''Auxilliary function that does the Wolfram API magic.'''

        apikey = self.config.get(u'wa:apikey', None)
        if apikey is None:
            return [u'Wolfram Alpha API key not configured, cannot use !wa.']
        try:
            url = u'http://api.wolframalpha.com/v2/query'
            payload = {
                u'appid': apikey,
                u'input': query,
                u'format': u'plaintext'
            }
            r = requests.get(url, timeout=10, params=payload)
            root = xml.etree.ElementTree.fromstring(r.text.encode(u'utf-8'))
            if root.get(u'success') != u'true':
                return [u'Wolfram Alpha found no answer.']
            plaintext = root.find(u'./pod[@primary="true"]/subpod/plaintext')
            if plaintext is None:
                for pod in root.findall(u'./pod'):
                    if pod.get(u'title') != u'Input interpretation':
                        plaintext = pod.find(u'./subpod/plaintext')
                        if plaintext is not None:
                            break
            if plaintext is None:
                return [u'Error: could not find response.']
            if plaintext.text is None:
                return [u'Error: empty response.']
            return plaintext.text.splitlines()
        except requests.exceptions.Timeout:
            return [u'Error: Wolfram Alpha timed out.']
        except xml.etree.ElementTree.ParseError:
            return [u'Error: could not parse response.']
        except Exception as e:
            log(e)
            return [u'Error: An unknown error occurred.']

    @command_handler(u'!wa (?P<query>.+)')
    def handle_wa(self, nick, channel, query=None):
        '''Ask something of the Wolfram Alpha API.'''

        log(u'{} used !wa'.format(nick))
        self.mb.clear(nick)
        result = self._aux_wa(query)

        # Private messages always get the full result
        if channel == PRIVMSG:
            self.mb.set(nick, result)
            return

        # Otherwise, check for the cooldown and respond accordingly.
        ltw = int(self.config.get(u'lasttime:wa', 0))
        ww = int(self.config.get(u'wait:wa', 0))
        if ltw < time.time() - ww:
            # If sending to the channel, send at most 5 lines.
            self.mb.set(channel, result[:5])
            self.config.set(u'lasttime:wa', time.time())
        else:
            self.mb.set(nick, result)
            wait = ltw + ww - int(time.time())
            r = u'I am cooling down. You cannot use !wa in '
            r += u'{} for another {} seconds.'.format(channel, wait)
            self.mb.add(nick, r)

    @command_handler(r'^!$')
    def handle_bang(self, nick, channel):
        '''Get messages from the message buffer.'''

        log(u'{} used !'.format(nick))
        pass

    @command_handler(u'^!help(\s(?P<topic>\w+))?')
    def handle_help(self, nick, channel, topic=None):
        '''Look up help about a topic'''

        log(u'{} used !help'.format(nick))

        self.mb.clear(nick)
        self._help(nick, topic)

    def _help(self, nick, topic):
        is_admin = self._is_admin(nick)
        rs = list()

        chan_code_ls = u'\x02, \x02'.join(self.channel_ids.keys())
        channelcodes = (u'Channel codes are \x02{}\x02.'.format(chan_code_ls))
        notpermitted = u'You are not permitted to use this command.'
        wiki = (u'More help is available at '
                u'https://github.com/williamjacksn/wormgas/wiki')

        if topic in [u'all', None]:
            rs.append(u'Use \x02!help [<topic>]\x02 with one of these topics: '
                      u'8ball, flip, id, key, nowplaying, prevplayed, roll, '
                      u'rps, rq, wa.')
            if is_admin:
                rs.append(u'Administration topics: restart, set, stop, unset.')
            rs.append(wiki)
        elif topic == u'8ball':
            rs.append(u'Use \x02!8ball\x02 to ask a question of the magic '
                      u'8ball.')
        elif topic == u'wa':
            rs.append(u'Use \x02!wa <query>\x02 to query Wolfram Alpha.')
        elif topic == u'flip':
            rs.append(u'Use \x02!flip\x02 to flip a coin.')
        elif topic == u'id':
            rs.append(u'Look up your Rainwave user id at '
                      u'http://rainwave.cc/auth/ and use \x02!id add <id>\x02 '
                      u'to tell me about it.')
            rs.append(u'Use \x02!id drop\x02 to delete your user id and '
                      u'\x02!id show\x02 to see it.')
        elif topic == u'key':
            rs.append(u'Get an API key from http://rainwave.cc/auth/ and use '
                      u'\x02!key add <key>\x02 to tell me about it.')
            rs.append(u'Use \x02!key drop\x02 to delete your key and \x02!key '
                      u'show\x02 to see it.')
        elif topic in [u'nowplaying', u'np']:
            rs.append(u'Use \x02!nowplaying <channel>\x02 to show what is now '
                      u'playing on the radio.')
            rs.append(u'Short version is \x02!np<channel>\x02.')
            rs.append(channelcodes)
        elif topic in [u'prevplayed', u'pp']:
            rs.append(u'Use \x02!prevplayed <channel> [<index>]\x02 to show '
                      u'what was previously playing on the radio.')
            rs.append(u'Short version is \x02!pp<channel> [<index>]\x02.')
            rs.append(u'Index should be one of (0, 1, 2), 0 is default, '
                      u'higher numbers are further in the past.')
            rs.append(channelcodes)
        elif topic == u'restart':
            if is_admin:
                rs.append(u'Use \x02!restart\x02 to restart the bot.')
            else:
                rs.append(notpermitted)
        elif topic == u'roll':
            rs.append(u'Use \x02!roll [#d^]\x02 to roll a ^-sided die # '
                      u'times.')
        elif topic == u'rps':
            rs.append(u'Use \x02!rock\x02, \x02!paper\x02, or '
                      u'\x02!scissors\x02 to play a game.')
            rs.append(u'Use \x02!rps record [<nick>]\x02 to see the record '
                      u'for <nick>, leave off <nick> to see your own record, '
                      u'use nick \'!global\' to see the global record.')
            rs.append(u'Use \x02!rps stats [<nick>]\x02 to see some '
                      u'statistics for <nick>, leave off <nick> to see your '
                      u'own statistics.')
            rs.append(u'Use \x02!rps reset\x02 to reset your record and '
                      u'delete your game history, there is no confirmation '
                      u'and this cannot be undone.')
            rs.append(u'Use \x02!rps who\x02 to see a list of known players')
            if is_admin:
                rs.append(u'Administrators can use \x02!rps rename <oldnick> '
                          u'<newnick>\x02 to reassign stats and game history '
                          u'from one nick to another.')
        elif topic == u'rq':
            rs.append(u'Use \x02!rq <song_id>\x02 to add a song to your '
                      u'request queue, find the <song_id> using '
                      u'\x02!lookup\x02 or \x02!unrated\x02.')
            rs.append(u'Use \x02!rq unrated\x02 to fill your request queue '
                      u'with unrated songs.')
            rs.append(u'Use \x02!rq fav\x02 to add favourite songs to your '
                      u'request queue.')
            rs.append(u'Use \x02!rq pause\x02 to pause your request queue).')
            rs.append(u'Use \x02!rq resume\x02 to resume your request queue).')
            rs.append(u'Use \x02!rq clear\x02 to remove all songs from your '
                      u'request queue.')
        elif topic == u'set':
            if is_admin:
                rs.append(u'Use \x02!set [<id>] [<value>]\x02 to display or '
                          u'change configuration settings.')
                rs.append(u'Leave off <value> to see the current setting.')
                rs.append(u'Leave off <id> and <value> to see a list of all '
                          u'available config ids.')
            else:
                rs.append(notpermitted)
        elif topic == u'stop':
            if is_admin:
                rs.append(u'Use \x02!stop\x02 to shut down the bot.')
            else:
                rs.append(notpermitted)
        elif topic == u'unset':
            if is_admin:
                rs.append(u'Use \x02!unset <id>\x02 to remove a configuration '
                          u'setting.')
            else:
                rs.append(notpermitted)
        else:
            rs.append(u'I cannot help you with \'{}\''.format(topic))
            rs.append(wiki)

        for r in rs:
            self.mb.add(nick, r)

    @command_handler(u'^!id(\s(?P<mode>\w+))?(\s(?P<uid>\d+))?')
    def handle_id(self, nick, channel, mode=None, uid=None):
        '''Manage correlation between an IRC nick and Rainwave User ID

        Arguments:
            mode: string, one of 'add', 'drop', 'show'
            uid: numeric, the person's Rainwave User ID'''

        log(u'{} used !id'.format(nick))

        self.mb.clear(nick)

        if mode == u'add' and uid:
            self.config.add_id_to_nick(uid, nick)
            r = u'I assigned the user id {} to nick \'{}\'.'.format(uid, nick)
            self.mb.add(nick, r)
        elif mode == u'drop':
            self.config.drop_id_for_nick(nick)
            r = u'I dropped the user id for nick \'{}\'.'.format(nick)
            self.mb.add(nick, r)
        elif mode == u'show':
            stored_id = self.config.get_id_for_nick(nick)
            if stored_id:
                r = u'The user id for \'{}\' is {}.'.format(nick, stored_id)
                self.mb.add(nick, r)
            else:
                r = u'I do not have a user id for nick \'{}\'.'.format(nick)
                self.mb.add(nick, r)
        else:
            self._help(nick, topic=u'id')

    @command_handler(u'^!key(\s(?P<mode>\w+))?(\s(?P<key>\w{10}))?')
    def handle_key(self, nick, channel, mode=None, key=None):
        '''Manage API keys

        Arguments:
            mode: string, one of 'add', 'drop', 'show'
            key: string, the API key to add'''

        log(u'{} used !key'.format(nick))

        self.mb.clear(nick)

        if mode == u'add' and key:
            self.config.add_key_to_nick(key, nick)
            r = u'I assigned the API key \'{}\' to \'{}\'.'.format(key, nick)
            self.mb.add(nick, r)
        elif mode == u'drop':
            self.config.drop_key_for_nick(nick)
            r = u'I dropped the API key for \'{}\'.'.format(nick)
            self.mb.add(nick, r)
        elif mode == u'show':
            stored_id = self.config.get_key_for_nick(nick)
            if stored_id:
                r = u'The API key for \'{}\' is'.format(nick)
                r = u'{} \'{}\'.'.format(r, stored_id)
                self.mb.add(nick, r)
            else:
                r = u'I do not have an API key for nick \'{}\'.'.format(nick)
                self.mb.add(nick, r)
        else:
            self._help(nick, topic=u'key')

    def handle_load(self, tokens):
        public = list()
        private = list()

        if len(tokens) < 2:
            private.append(u'Please specify a plugin to load.')
            return public, private

        plug_name = tokens[1]
        module_name = u'plugins.{}'.format(plug_name)
        if module_name in sys.modules:
            module = reload(sys.modules[module_name])
        else:
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                err = u'Error while loading plugin: {}.'.format(plug_name)
                log(err)
                private.append(err)
                return public, private

        plugins = set(self.config.get(u'plugins', list()))
        plugins.add(plug_name)
        self.config.set(u'plugins', list(plugins))
        for plug_handler in inspect.getmembers(module, inspect.isclass):
            cls = plug_handler[1]
            cmd_dict = _plug_commands
            if cls.admin:
                cmd_dict = _plug_commands_admin
            for cmd in cls.cmds:
                cmd_dict[cmd] = cls.handle
                private.append(u'Loaded a command: {}.'.format(cmd))

        return public, private

    def handle_unload(self, tokens):
        public = list()
        private = list()

        if len(tokens) < 2:
            private.append(u'Please specify a plugin to load.')
            return public, private

        plug_name = tokens[1]
        module_name = u'plugins.{}'.format(plug_name)

        plugins = set(self.config.get(u'plugins', list()))
        if plug_name in plugins:
            plugins.remove(plug_name)
            self.config.set(u'plugins', list(plugins))

        if module_name in sys.modules:
            module = sys.modules.get(module_name)
            for plug_handler in inspect.getmembers(module, inspect.isclass):
                cls = plug_handler[1]
                cmd_dict = _plug_commands
                if cls.admin:
                    cmd_dict = _plug_commands_admin
                for cmd in cls.cmds:
                    if cmd in cmd_dict:
                        del cmd_dict[cmd]
                        private.append(u'Unloaded a command: {}'.format(cmd))
                    else:
                        private.append(u'Command not found: {}'.format(cmd))
        else:
            private.append(u'Plugin not loaded: {}'.format(plug_name))

        return public, private

    @command_handler(u'!restart')
    def handle_restart(self, nick, channel):
        '''Restart the bot'''

        log(u'{} used !restart'.format(nick))

        if self._is_admin(nick):
            self.config.set(u'restart_on_stop', 1)
            self.handle_stop(nick, channel)
        else:
            log(u'{} does not have privs to use !restart'.format(nick))

    @command_handler(u'!(?P<mode>rock|paper|scissors)')
    def handle_rps(self, nick, channel, mode=None):
        '''Rock, paper, scissors'''

        if mode is None:
            return
        else:
            mode = mode.lower()

        log(u'{} used !{}'.format(nick, mode))

        self.mb.clear(nick)

        rps = [u'rock', u'paper', u'scissors']
        challenge = rps.index(mode)
        response = random.randint(0, 2)

        self.config.log_rps(nick, challenge, response)

        r = u'You challenge with {}. I counter with'.format(mode)
        r = u'{} {}. '.format(r, rps[response])

        if challenge == (response + 1) % 3:
            r += u'You win!'
        elif challenge == response:
            r += u'We draw!'
        elif challenge == (response + 2) % 3:
            r += u'You lose!'

        w, d, l = self.config.get_rps_record(nick)
        pw = int(float(w) / float(w + d + l) * 100)
        pd = int(float(d) / float(w + d + l) * 100)
        pl = int(float(l) / float(w + d + l) * 100)
        r += u' Your current record is '
        r += u'{}-{}-{} or {}%-{}%-{}% (w-d-l).'.format(w, d, l, pw, pd, pl)

        if channel == PRIVMSG:
            self.mb.add(nick, r)
            return

        ltr = int(self.config.get(u'lasttime:rps', 0))
        wr = int(self.config.get(u'wait:rps', 0))
        if ltr < time.time() - wr:
            self.mb.add(channel, r)
            self.config.set(u'lasttime:rps', time.time())
        else:
            self.mb.add(nick, r)
            wait = ltr + wr - int(time.time())
            r = u'I am cooling down. You cannot use !{}'.format(mode)
            r = u'{} in {} for another {} seconds.'.format(r, channel, wait)
            self.mb.add(nick, r)

    @command_handler(u'^!rps record(\s(?P<target>\S+))?')
    def handle_rps_record(self, nick, channel, target=None):
        '''Report RPS record for a nick'''

        log(u'{} used !rps record'.format(nick))

        self.mb.clear(nick)

        if target is None:
            target = nick

        w, d, l = self.config.get_rps_record(target)
        total = sum((w, d, l))
        r = u'RPS record for {} ({} game'.format(target, total)
        if total != 1:
            r += u's'
        r += u') is {}-{}-{} (w-d-l).'.format(w, d, l)

        if channel == PRIVMSG:
            self.mb.add(nick, r)
            return

        ltr = int(self.config.get(u'lasttime:rps', 0))
        wr = int(self.config.get(u'wait:rps', 0))
        if ltr < time.time() - wr:
            self.mb.add(channel, r)
            self.config.set(u'lasttime:rps', time.time())
        else:
            self.mb.add(nick, r)
            wait = ltr + wr - int(time.time())
            m = u'I am cooling down. You cannot use !rps in '
            m += u'{} for another {} seconds.'.format(channel, wait)
            self.mb.add(nick, m)

    @command_handler(u'!rps rename(\s(?P<old>\S+))?(\s(?P<new>\S+))?')
    def handle_rps_rename(self, nick, channel, old=None, new=None):
        '''Rename an RPS nick, useful for merging game histories'''

        log(u'{} used !rps rename'.format(nick))

        if self._is_admin(nick) and old and new:
            self.mb.clear(nick)
            self.config.rename_rps_player(old, new)
            r = u'I assigned RPS game history for {} to {}.'.format(old, new)
            self.mb.add(nick, r)

    @command_handler(u'^!rps reset')
    def handle_rps_reset(self, nick, channel):
        '''Reset RPS stats and delete game history for a nick'''

        log(u'{} used !rps reset'.format(nick))

        self.mb.clear(nick)

        self.config.reset_rps_record(nick)
        r = u'I reset your RPS record and deleted your game history.'
        self.mb.add(nick, r)

    @command_handler(u'!rps stats(\s(?P<target>\S+))?')
    def handle_rps_stats(self, nick, channel, target=None):
        '''Get some RPS statistics for a player'''

        log(u'{} used !rps stats'.format(nick))

        self.mb.clear(nick)

        if target is None:
            target = nick

        totals = self.config.get_rps_challenge_totals(target)
        games = sum(totals)
        if games > 0:
            r_rate = totals[0] / float(games) * 100
            p_rate = totals[1] / float(games) * 100
            s_rate = totals[2] / float(games) * 100

            r = target
            r += u' challenges with rock/paper/scissors at these rates: '
            r += u'{:3.1f}/{:3.1f}/{:3.1f}%.'.format(r_rate, p_rate, s_rate)
        else:
            r = u'{} does not play. :('.format(target)

        if channel == PRIVMSG:
            self.mb.add(nick, r)
            return

        ltr = int(self.config.get(u'lasttime:rps', 0))
        wr = int(self.config.get(u'wait:rps', 0))
        if ltr < time.time() - wr:
            self.mb.add(channel, r)
            self.config.set(u'lasttime:rps', time.time())
        else:
            self.mb.add(nick, r)
            wait = ltr + wr - int(time.time())
            r = u'I am cooling down. You cannot use !rps in {}'.format(channel)
            r = u'{} for another {} seconds.'.format(r, wait)
            self.mb.add(nick, r)

    @command_handler(u'^!rps who')
    def handle_rps_who(self, nick, channel):
        '''List all players in the RPS game history'''

        log(u'{} used !rps who'.format(nick))

        self.mb.clear(nick)

        players = self.config.get_rps_players()

        mlnl = int(self.config.get(u'maxlength:nicklist', 10))
        while len(players) > mlnl:
            plist = players[:mlnl]
            players[:mlnl] = []
            r = u'RPS players: ' + u', '.join(plist)
            self.mb.add(nick, r)
        r = u'RPS players: ' + u', '.join(players)
        self.mb.add(nick, r)

    @command_handler(u'^!set(\s(?P<id>\S+))?(\s(?P<value>.+))?')
    def handle_set(self, nick, channel, id=None, value=None):
        '''View and set bot configuration'''

        log(u'{} used !set'.format(nick))

        self.mb.clear(nick)

        if self._is_admin(nick):
            self.mb.set(nick, self.config.handle(id, value))
        else:
            log(u'{} does not have privs to use !set'.format(nick))

    @command_handler(u'!stop')
    def handle_stop(self, nick, channel):
        '''Shut down the bot'''

        log(u'{} used !stop'.format(nick))

        if self._is_admin(nick):
            if self.config.get(u'restart_on_stop'):
                self.config.unset(u'restart_on_stop')
                pid = subprocess.Popen(
                    [_abspath],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE)
            self.die(u'I was stopped by {}'.format(nick))
        else:
            log(u'{} does not have privs to use !stop'.format(nick))

    @command_handler(u'^!unset(\s(?P<id>\S+))?')
    def handle_unset(self, nick, channel, id=None):
        '''Unset a configuration item'''

        log(u'{} used !unset'.format(nick))

        if self._is_admin(nick):
            if id:
                self.config.unset(id)
                self.mb.clear(nick)
                self.mb.add(nick, u'{} has been unset.'.format(id))
                return
        else:
            log(u'{} does not have privs to use !unset'.format(nick))

    def on_join(self, c, e):
        '''This method is called when an IRC join event happens

        Arguments:
            c: the Connection object asociated with this event
            e: the Event object'''

        nick = e.source.nick
        irc_chan = e.target

        # Check for a join response
        jr = self.config.get(u'joinresponse:{}'.format(nick))
        if jr:
            self._to_irc(c, u'privmsg', irc_chan, jr)

        ja = self.config.get(u'joinaction:{}'.format(nick))
        if ja:
            self._to_irc(c, u'action', irc_chan, ja)

    def on_ping(self, c, e):
        '''This method is called when an IRC ping event happens'''

        # Start the periodic tasks.
        self._periodic(c)

    def on_privmsg(self, c, e):
        '''This method is called when a message is sent directly to the bot

        Arguments:
            c: the Connection object associated with this event
            e: the Event object'''

        nick = e.source.nick
        me = e.target
        msg = e.arguments[0].strip()
        chan = self.config.get(u'irc:channel')

        command_handled = False

        # Core commands
        tokens = msg.split()
        if len(tokens) == 0:
            return
        cmd = tokens[0].lower()
        if cmd == u'!load':
            command_handled = True
            if self._is_admin(nick):
                public, private = self.handle_load(tokens)
                self.mb.set(chan, public)
                self.mb.set(nick, private)
            else:
                self.mb.add(nick, u'You are not an admin.')

        if cmd == u'!unload':
            command_handled = True
            if self._is_admin(nick):
                public, private = self.handle_unload(tokens)
                self.mb.set(chan, public)
                self.mb.set(nick, private)
            else:
                self.mb.add(nick, u'You are not an admin.')

        # Try admin commands from plugins
        if not command_handled:
            if self._is_admin(nick) and cmd in _plug_commands_admin:
                command_handled = True
                handler = _plug_commands_admin.get(cmd)
                try:
                    public, private = handler(nick, me, tokens, self.config)
                    self.mb.set(chan, public)
                    self.mb.set(nick, private)
                except:
                    log(u'Exception in {}'.format(cmd))
                    m = (u'I experienced a problem and recorded some '
                         u'exception information in the log.')
                    self.mb.set(nick, [m])

        # Try normal commands from plugins
        if not command_handled:
            if cmd in _plug_commands:
                command_handled = True
                handler = _plug_commands.get(cmd)
                try:
                    public, private = handler(nick, me, tokens, self.config)
                    self.mb.set(chan, public)
                    self.mb.set(nick, private)
                except:
                    log(u'Exception in {}'.format(cmd))
                    m = (u'I experienced a problem and recorded some '
                         u'exception information in the log.')
                    self.mb.set(nick, [m])

        # Try all the decorated command handlers
        for command in _commands:
            if command(self, nick, msg, PRIVMSG):
                command_handled = True
                break

        if not command_handled:
            # No responses from the commands, punt to the brain
            self.mb.clear(nick)
            self.mb.add(nick, self._talk(msg))

        # Send responses
        while self.mb.items(chan):
            self._to_irc(c, u'privmsg', chan, self.mb.pop(chan, 0))

        rs = list()
        while len(rs) < 7 and self.mb.items(nick):
            rs.append(self.mb.pop(nick, 0))

        if len(self.mb.items(nick)) == 1:
            rs.append(self.mb.pop(nick, 0))

        if len(self.mb.items(nick)) > 1:
            num = len(self.mb.items(nick))
            r = u'Use \x02!\x02 to see more messages ({} left).'.format(num)
            rs.append(r)

        for r in rs:
            self._to_irc(c, u'privmsg', nick, r)

    def on_pubmsg(self, c, e):
        '''This method is called when a message is sent to the channel the bot
        is on

        Arguments:
            c: the Connection object associated with this event
            e: the Event object'''

        nick = e.source.nick
        msg = e.arguments[0].strip()
        chan = e.target

        command_handled = False

        # Core commands
        tokens = msg.split()
        if len(tokens) == 0:
            return
        cmd = tokens[0].lower()
        if cmd == u'!load':
            command_handled = True
            if self._is_admin(nick):
                public, private = self.handle_load(tokens)
                self.mb.set(chan, public)
                self.mb.set(nick, private)
            else:
                self.mb.add(nick, u'You are not an admin.')

        if cmd == u'!unload':
            command_handled = True
            if self._is_admin(nick):
                public, private = self.handle_unload(tokens)
                self.mb.set(chan, public)
                self.mb.set(nick, private)
            else:
                self.mb.add(nick, u'You are not an admin.')

        # Try admin commands from plugins
        if not command_handled:
            if self._is_admin(nick) and cmd in _plug_commands_admin:
                command_handled = True
                handler = _plug_commands_admin.get(cmd)
                try:
                    public, private = handler(nick, chan, tokens, self.config)
                    self.mb.set(chan, public)
                    self.mb.set(nick, private)
                except:
                    log(u'Exception in {}'.format(cmd))
                    m = (u'I experienced a problem and recorded some '
                         u'exception information in the log.')
                    self.mb.set(nick, [m])

        # Try normal commands from plugins
        if not command_handled:
            if cmd in _plug_commands:
                command_handled = True
                handler = _plug_commands.get(cmd)
                try:
                    public, private = handler(nick, chan, tokens, self.config)
                    self.mb.set(chan, public)
                    self.mb.set(nick, private)
                except:
                    log(u'Exception in {}'.format(cmd))
                    m = (u'I experienced a problem and recorded some '
                         u'exception information in the log.')
                    self.mb.set(nick, [m])

        # Try all the decorated command handlers
        if not command_handled:
            for command in _commands:
                if command(self, nick, msg, chan):
                    command_handled = True
                    break

        # If there are no responses from the commands, look for URLs
        title_found = False
        if not command_handled:
            urls = self._find_urls(msg)
            for url in urls:
                title = None
                try:
                    title = self.tf.get_title(url)
                except util.TitleFetcherError as err:
                    log(err)
                if title:
                    log(u'Found a title: {}'.format(title))
                    title_found = True
                    self.mb.add(chan, u'[ {} ]'.format(title))

        # If there are no URLs, punt to the brain
        if not (command_handled or title_found):
            talkr = self._talk(msg)
            if talkr:
                self.config.set(u'msg:last', msg)
                self.config.set(u'lasttime:msg', time.time())
                ltr = int(self.config.get(u'lasttime:respond', 0))
                wr = int(self.config.get(u'wait:respond', 0))

                if self.config.get(u'irc:nick') in msg:
                    if time.time() > ltr + wr:
                        self.mb.add(chan, talkr)
                        self.config.set(u'msg:last', talkr)
                        self.config.set(u'lasttime:respond', time.time())
                    else:
                        self._to_irc(c, u'privmsg', nick, talkr)
                        wait = ltr + wr - int(time.time())
                        r = u'I am cooling down. I cannot respond in '
                        r += u'{} for another {} seconds.'.format(chan, wait)
                        self._to_irc(c, u'privmsg', nick, r)

        # Send responses
        while self.mb.items(chan):
            r = u'{}: {}'.format(nick, self.mb.pop(chan, 0))
            self._to_irc(c, u'privmsg', chan, r)

        if command_handled:
            rs = list()
            while len(rs) < 7 and self.mb.items(nick):
                rs.append(self.mb.pop(nick, 0))

            if len(self.mb.items(nick)) == 1:
                rs.append(self.mb.pop(nick, 0))

            if len(self.mb.items(nick)) > 1:
                n = len(self.mb.items(nick))
                r = u'Use \x02!\x02 to see more messages ({} left).'.format(n)
                rs.append(r)

            for r in rs:
                self._to_irc(c, u'privmsg', nick, r)

    def on_welcome(self, c, e):
        '''This method is called when the bot first connects to the server

        Arguments:
            c: the Connection object associated with this event
            e: the Event object'''

        passwd = self.config.get(u'irc:nickservpass')
        if passwd is not None:
            m = u'identify {}'.format(passwd)
            self._to_irc(c, u'privmsg', u'nickserv', m)
        c.join(self.config.get(u'irc:channel'))

    def _events_not_logged(self):
        return [
            u'all_raw_messages',
            u'created',
            u'endofmotd',
            u'featurelist',
            u'luserchannels',
            u'luserclient',
            u'luserme',
            u'luserop',
            u'luserunknown',
            u'motd',
            u'motdstart',
            u'myinfo',
            u'n_global',
            u'n_local'
        ]

    def _find_urls(self, text):
        '''Look for URLs in arbitrary text. Return a list of the URLs found.'''

        log(u'Looking for URLs in: {}'.format(text))

        urls = []
        for token in text.split():
            try:
                o = urlparse.urlparse(token)
            except ValueError:
                log(u'Trouble looking for URLs.')
                return urls
            if u'http' in o.scheme and o.netloc:
                url = o.geturl()
                log(u'Found a URL: {}'.format(url))
                urls.append(url)
        return urls

    def _is_admin(self, nick):
        '''Check whether a nick has privileges to use admin commands'''

        channel = self.config.get(u'irc:channel').encode(u'ascii')
        if channel in self.channels:
            chan = self.channels[channel]
            if nick in chan.owners():
                return True
            elif nick in chan.opers():
                return True
            elif nick in chan.halfops():
                return True

        return False

    def _periodic(self, c):
        # If I have not checked for forum activity for 'timeout:forumcheck'
        # seconds, check now

        log(u'Performing periodic tasks')

        chan = self.config.get(u'irc:channel')

        ltm = int(self.config.get(u'lasttime:msg', 0))
        toc = int(self.config.get(u'timeout:chat', 3600))
        if int(time.time()) > ltm + toc:
            log(u'Chat timeout exceeded, keep the conversation moving')
            talkr = self._talk()
            if talkr:
                self.config.set(u'msg:last', talkr)
                self.config.set(u'lasttime:msg', time.time())
                self.config.set(u'lasttime:respond', time.time())
                self.mb.add(chan, talkr)

        while self.mb.items(chan):
            self._to_irc(c, u'privmsg', chan, self.mb.pop(chan, 0))

    quotes = [
        (u'Attack the evil that is within yourself, rather than attacking the '
         u'evil that is in others.'),
        u'Before you embark on a journey of revenge, dig two graves.',
        u'Better a diamond with a flaw than a pebble without.',
        u'Everything has beauty, but not everyone sees it.',
        u'He who knows all the answers has not been asked all the questions.',
        (u'He who learns but does not think, is lost! He who thinks but does '
         u'not learn is in great danger.'),
        u'I hear and I forget. I see and I remember. I do and I understand.',
        (u'If what one has to say is not better than silence, then one should '
         u'keep silent.'),
        (u'If you make a mistake and do not correct it, this is called a '
         u'mistake.'),
        (u'Ignorance is the night of the mind but a night without moon and '
         u'star.'),
        (u'Music produces a kind of pleasure which human nature cannot do '
         u'without.'),
        u'Only the wisest and stupidest of men never change.',
        (u'Our greatest glory is not in never falling, but in rising every '
         u'time we fall.'),
        u'Respect yourself and others will respect you.',
        u'Silence is a true friend who never betrays.',
        (u'The hardest thing of all is to find a black cat in a dark room, '
         u'especially if there is no cat.'),
        (u'The man who asks a question is a fool for a minute, the man who '
         u'does not ask is a fool for life.'),
        (u'The superior man is modest in his speech, but exceeds in his '
         u'actions.'),
        u'To be wronged is nothing, unless you continue to remember it.',
        (u'To see what is right and not to do it, is want of courage or of '
         u'principle.'),
        (u'What you know, you know, what you don\'t know, you don\'t know. '
         u'This is true wisdom.')
    ]

    def _talk(self, msg=None):
        '''Engage the brain, respond when appropriate

        Arguments:
            msg: the message to learn and possible reply to

        Returns: a string'''

        # If I am not replying to anything in particular, use the last message
        if msg is None:
            msg = self.config.get(u'msg:last')
        if msg is None:
            return random.choice(self.quotes)

        # Ignore messages with certain words
        if self.reignore:
            result = self.reignore.search(msg)
            if result is not None:
                return random.choice(self.quotes)

        # Clean up the message before sending to the brain
        tobrain = msg
        tobrain = tobrain.replace(self.config.get(u'irc:nick'), u'')
        tobrain = tobrain.replace(u':', u'')

        self.brain.learn(tobrain)

        return self.brain.reply(tobrain)

    def _to_irc(self, c, msgtype, target, msg):
        '''Send an IRC message'''

        log(u'Sending {} to {} -- {}'.format(msgtype, target, msg))

        if hasattr(c, msgtype):
            f = getattr(c, msgtype)
            if type(msg) is not unicode:
                msg = unicode(msg, u'utf-8')
            try:
                f(target, msg)
            except:
                log(u'Problem sending to IRC')
        else:
            log(u'Invalid message type \'{}\''.format(msgtype))


def main():
    bot = Wormgas()
    bot.start()

if __name__ == u'__main__':
    main()
