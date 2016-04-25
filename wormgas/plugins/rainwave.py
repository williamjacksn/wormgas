import datetime
import enum
import json
import pytz
import time
import urllib.parse
import urllib.request
import uuid


class RainwaveChannel(enum.Enum):
    game = 1
    rw = 1
    oc = 2
    ocr = 2
    cover = 3
    covers = 3
    mw = 3
    vw = 3
    bw = 4
    ch = 4
    chip = 4
    all = 5
    omni = 5
    ow = 5

    @property
    def channel_id(self):
        return self.value

    @property
    def long_name(self):
        return '{} channel'.format(self.short_name)

    @property
    def short_name(self):
        return (None, 'Game', 'OCR', 'Covers', 'Chiptune', 'All')[self.value]

    @property
    def url(self):
        subdomains = ('', 'game.', 'ocr.', 'covers.', 'chiptune.', 'all.')
        return 'http://{}rainwave.cc/'.format(subdomains[self.value])


class RainwaveHandler:
    cmds = []
    admin = False
    help_text = []

    NICK_NOT_RECOGNIZED = ('I do not recognize you. If your nick does not '
                           'match your Rainwave username, use \x02!id\x02 to '
                           'link your Rainwave account to your nick.')

    MISSING_KEY = ('I do not have a key stored for you. Visit '
                   'http://rainwave.cc/keys/ to get a key and tell me about '
                   'it with \x02!key add <key>\x02.')

    codes = [code for code in RainwaveChannel.__members__.keys()]
    chan_code_ls = '\x02, \x02'.join(codes)
    channel_codes = 'Channel codes are \x02{}\x02.'.format(chan_code_ls)

    @staticmethod
    def _call(path, params=None):
        if params is None:
            params = {}
        base_url = 'http://rainwave.cc/api4/'
        url = '{}{}'.format(base_url, path.lstrip('/'))
        data = urllib.parse.urlencode(params).encode()
        headers = {'user-agent': str(uuid.uuid4())}
        request = urllib.request.Request(url, data, headers)
        response = urllib.request.urlopen(request)
        if response.status == 200:
            body = response.read().decode()
            return json.loads(body)
        raise RuntimeError

    @staticmethod
    def artist_string(artists):
        return ', '.join([a.get('name') for a in artists])

    def song_string(self, song, simple=False):
        m = '{} //'.format(song.get('albums')[0].get('name'))
        artists = self.artist_string(song.get('artists'))
        m = '{} {} // {}'.format(m, song.get('title'), artists)

        if simple:
            return m

        url = song.get('url')
        if url is not None:
            m = '{} [ {} ]'.format(m, url)

        vote_count = song.get('entry_votes', 0)
        m = '{} ({} vote'.format(m, vote_count)
        if int(vote_count) != 1:
            m = '{}s'.format(m)

        m = '{}, rated {}'.format(m, song.get('rating'))

        elec_request_username = song.get('elec_request_username')
        if elec_request_username is not None:
            m = '{}, requested by {}'.format(m, elec_request_username)

        m = '{})'.format(m)
        return m

    def get_api_auth_for_nick(self, nick, bot):
        auth = {'user_id': self.get_id_for_nick(nick, bot)}
        user_id = auth.get('user_id')
        auth['key'] = self.get_key_for_nick(nick, bot)
        auth['chan'] = self.get_current_channel_for_id(user_id, bot)
        return auth

    def get_current_channel_for_id(self, listener_id, bot):
        if listener_id is None:
            return None
        user_id = bot.c.get('rainwave:user_id')
        key = bot.c.get('rainwave:key')
        d = self.rw_listener(user_id, key, listener_id)
        listener_name = d.get('listener').get('name')
        return self.get_current_channel_for_name(listener_name, bot)

    def get_current_channel_for_name(self, name, bot):
        user_id = bot.c.get('rainwave:user_id')
        key = bot.c.get('rainwave:key')
        d = self.rw_user_search(user_id, key, name)
        chan_id = d.get('user').get('sid')
        if chan_id is None:
            return None
        return RainwaveChannel(int(chan_id))

    def get_id_for_nick(self, nick, bot):
        rw_config = self.get_rw_config(bot)
        listener_id = rw_config.get(nick, {}).get('id')
        if listener_id is None:
            user_id = bot.c.get('rainwave:user_id')
            key = bot.c.get('rainwave:key')
            d = self.rw_user_search(user_id, key, nick)
            listener_id = d.get('user').get('user_id')
        return listener_id

    def get_key_for_nick(self, nick, bot):
        rw_config = self.get_rw_config(bot)
        return rw_config.get(nick, {}).get('key')

    @staticmethod
    def get_rw_config(bot):
        rw_config_path = bot.c.path.with_name('_rainwave.json')
        return bot.c.__class__(rw_config_path)

    def rw_admin_list_producers_all(self, user_id, key):
        params = {
            'user_id': user_id,
            'key': key
        }
        return self._call('admin/list_producers_all', params=params)

    def rw_clear_requests(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return self._call('clear_requests', params=params)

    def rw_current_listeners(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return self._call('current_listeners', params=params)

    def rw_info(self, sid):
        params = {'sid': sid}
        return self._call('info', params=params)

    def rw_info_all(self):
        params = {'sid': 1}
        return self._call('info_all', params=params)

    def rw_listener(self, user_id, key, listener_id):
        params = {
            'user_id': user_id,
            'key': key,
            'id': listener_id
        }
        return self._call('listener', params=params)

    def rw_pause_request_queue(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return self._call('pause_request_queue', params=params)

    def rw_request(self, user_id, key, sid, song_id):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid,
            'song_id': song_id
        }
        return self._call('request', params=params)

    def rw_request_favorited_songs(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return self._call('request_favorited_songs', params=params)

    def rw_request_unrated_songs(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return self._call('request_unrated_songs', params=params)

    def rw_song(self, user_id, key, sid, song_id):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid,
            'id': song_id
        }
        return self._call('song', params=params)

    def rw_unpause_request_queue(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return self._call('unpause_request_queue', params=params)

    def rw_user_search(self, user_id, key, username):
        params = {
            'user_id': user_id,
            'key': key,
            'username': username
        }
        return self._call('user_search', params=params)

    def rw_vote(self, user_id, key, sid, entry_id):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid,
            'entry_id': entry_id
        }
        return self._call('vote', params=params)

    def send_help(self, target, bot):
        for line in self.help_text:
            bot.send_privmsg(target, line)


class SpecialEventTopicHandler(RainwaveHandler):
    cmds = []
    admin = True
    help_topic = 'power_hour_topics'
    help_text = [('I will automatically change the topic when there is a Power '
                  'Hour currently running.')]

    def __init__(self, sbot):
        @sbot.ee.on('PING')
        def check_special_events(_, bot):
            channel = bot.c['irc:channel']
            if not bot.in_channel:
                return
            new_topic_head = 'Welcome to Rainwave!'
            event_now = False
            events = self.get_current_events()
            future_events = self.get_future_events(bot)
            if events:
                event_now = True
                new_topic_head = ' '.join([e['text'] for e in events])
            elif future_events:
                new_topic_head = future_events[0]
            if bot.topics.get(channel) is None:
                bot.topics[channel] = ''
            topic_parts = bot.topics[channel].split(' | ')
            if new_topic_head != topic_parts[0]:
                topic_parts[0] = new_topic_head
                bot.send_topic(bot.c['irc:channel'], ' | '.join(topic_parts))
                if event_now:
                    for e in events:
                        m = '{text} {chan_url}'.format(**e)
                        bot.send_privmsg(bot.c['irc:channel'], m)

    @staticmethod
    def build_event_dict(chan, info):
        event = {'chan_id': chan.channel_id, 'chan_url': chan.url,
                 'chan_short_name': chan.short_name,
                 'name': '{} Power Hour'.format(info['event_name'])}
        event['text'] = '[{chan_short_name}] {name} on now!'.format(**event)
        return event

    def get_current_events(self):
        current_events = list()
        d = self.rw_info_all()
        for sid, info in d.get('all_stations_info', {}).items():
            if info['event_type'] == 'OneUp':
                chan = RainwaveChannel(int(sid))
                event = self.build_event_dict(chan, info)
                current_events.append(event)
        return current_events

    def get_future_events(self, bot):
        future_events = list()
        user_id = bot.c.get('rainwave:user_id')
        key = bot.c.get('rainwave:key')
        d = self.rw_admin_list_producers_all(user_id=user_id, key=key)
        for p in d.get('producers', []):
            if p['type'] == 'OneUpProducer':
                chan = RainwaveChannel(p['sid'])
                e_name = p['name']
                e_text = '[{}] {} Power Hour'.format(chan.short_name, e_name)
                when = pytz.timezone('US/Eastern').localize(datetime.datetime.fromtimestamp(p['start']))
                month = when.strftime('%b')
                w_time = when.strftime('%H:%M')
                e_text = '{}: {} {}'.format(e_text, month, when.day)
                e_text = '{} {} Eastern'.format(e_text, w_time)
                future_events.append(e_text)
        return future_events


class IdHandler(RainwaveHandler):
    cmds = ['!id']
    admin = False
    help_topic = 'id'
    help_text = [('Look up your Rainwave user id at http://rainwave.cc/auth/ '
                  'and use \x02!id add <id>\x02 to tell me about it.'),
                 ('Use \x02!id drop\x02 to delete your user id and \x02!id '
                  'show\x02 to see it.')]

    def handle(self, sender, _, tokens, bot):
        rw_config = self.get_rw_config(bot)

        if len(tokens) < 2:
            self.send_help(sender, bot)
            return

        action = tokens[1]
        if action == 'add':
            if len(tokens) > 2:
                uid = tokens[2]
                user_dict = rw_config.get(sender, {})
                user_dict['id'] = uid
                rw_config[sender] = user_dict
                m = 'I assigned the user id {} to {}.'
                bot.send_privmsg(sender, m.format(uid, sender))
            else:
                self.send_help(sender, bot)
        elif action == 'drop':
            user_dict = rw_config.get(sender, {})
            if 'id' in user_dict:
                del user_dict['id']
            rw_config[sender] = user_dict
            m = 'I dropped the user id for {}.'.format(sender)
            bot.send_privmsg(sender, m)
        elif action == 'show':
            user_dict = rw_config.get(sender, {})
            if 'id' in user_dict:
                m = 'The user id for {} is {}.'.format(sender, user_dict['id'])
                bot.send_privmsg(sender, m)
            else:
                m = 'I do not have a user id for {}.'.format(sender)
                bot.send_privmsg(sender, m)
        else:
            self.send_help(sender, bot)


class KeyHandler(RainwaveHandler):
    cmds = ['!key']
    admin = False
    help_topic = 'key'
    help_text = [('Get an API key from http://rainwave.cc/auth/ and use '
                  '\x02!key add <key>\x02 to tell me about it.'),
                 ('Use \x02!key drop\x02 to delete your key and \x02!key '
                  'show\x02 to see it.')]

    def handle(self, sender, _, tokens, bot):
        rw_config = self.get_rw_config(bot)

        if len(tokens) < 2:
            self.send_help(sender, bot)
            return

        action = tokens[1]
        if action == 'add':
            if len(tokens) > 2:
                key = tokens[2]
                user_dict = rw_config.get(sender, {})
                user_dict['key'] = key
                rw_config[sender] = user_dict
                m = 'I assigned the API key {} to {}.'
                bot.send_privmsg(sender, m.format(key, sender))
            else:
                self.send_help(sender, bot)
        elif action == 'drop':
            user_dict = rw_config.get(sender, {})
            if 'key' in user_dict:
                del user_dict['key']
            rw_config[sender] = user_dict
            m = 'I dropped the API key for {}.'.format(sender)
            bot.send_privmsg(sender, m)
        elif action == 'show':
            user_dict = rw_config.get(sender, {})
            if 'key' in user_dict:
                key = user_dict['key']
                m = 'The API key for {} is {}.'.format(sender, key)
                bot.send_privmsg(sender, m)
            else:
                m = 'I do not have an API key for {}.'.format(sender)
                bot.send_privmsg(sender, m)
        else:
            self.send_help(sender, bot)


class ListenerStatsHandler(RainwaveHandler):
    cmds = ['!lstats']
    admin = False
    help_topic = 'lstats'
    help_text = [('Use \x02!lstats\x02 to see information about current '
                  'Rainwave radio listeners.')]

    def handle(self, sender, target, tokens, bot):
        m = 'Registered listeners: '
        total = 0
        user_id = bot.c.get('rainwave:user_id')
        key = bot.c.get('rainwave:key')
        for chan in RainwaveChannel:
            d = self.rw_current_listeners(user_id, key, chan.channel_id)
            count = len(d.get('current_listeners'))
            m = '{}{} = {}, '.format(m, chan.long_name, count)
            total += count
        m = '{}Total = {}'.format(m, total)

        if not bot.is_irc_channel(target):
            bot.send_privmsg(sender, m)
            return

        now = int(time.time())
        last = int(bot.c.get('rainwave:lstats:last', 0))
        wait = int(bot.c.get('rainwave:lstats:wait', 0))
        if last < now - wait:
            bot.send_privmsg(target, m)
            bot.c.set('rainwave:lstats:last', now)
        else:
            bot.send_privmsg(sender, m)
            remaining = last + wait - now
            m = 'I am cooling down. You cannot use {}'.format(tokens[0])
            m = '{} in {} for another'.format(m, target)
            m = '{} {} seconds.'.format(m, remaining)
            bot.send_privmsg(sender, m)


class NextHandler(RainwaveHandler):
    cmds = ['!next', '!nx', '!nxall', '!nxbw', '!nxch', '!nxchip',
            '!nxcover', '!nxcovers', '!nxgame', '!nxmw', '!nxoc',
            '!nxocr', '!nxomni', '!nxow', '!nxrw', '!nxvw']
    admin = False
    help_topic = 'next'
    help_text = [('Use \x02!next [<channel>]\x02 to show what is up next on '
                  'the radio.'),
                 'Short version is \x02!nx[<channel>]\x02.',
                 RainwaveHandler.channel_codes,
                 ('Leave off <channel> to auto-detect the channel you are '
                  'tuned to.')]

    def handle(self, sender, target, tokens, bot):
        cmd = tokens[0].lower()

        chan = None
        idx = 0

        if cmd in ['!nxgame', '!nxrw']:
            chan = RainwaveChannel.game
        elif cmd in ['!nxoc', '!nxocr']:
            chan = RainwaveChannel.ocr
        elif cmd in ['!nxcover', '!nxcovers', '!nxmw', '!nxvw']:
            chan = RainwaveChannel.covers
        elif cmd in ['!nxbw', '!nxch', '!nxchip']:
            chan = RainwaveChannel.chip
        elif cmd in ['!nxall', '!nxomni', '!nxow']:
            chan = RainwaveChannel.all
        elif cmd in ['!next', '!nx']:
            if len(tokens) > 1:
                if tokens[1].lower() in RainwaveChannel.__members__.keys():
                    chan = RainwaveChannel[tokens[1].lower()]
            if chan is None:
                listener_id = self.get_id_for_nick(sender, bot)
                chan = self.get_current_channel_for_id(listener_id, bot)
            if chan is None:
                m = 'You are not tuned in and you did not specify a valid'
                m = '{} channel code.'.format(m)
                bot.send_privmsg(sender, m)
                return

        m = 'Next up on the {}'.format(chan.long_name)
        d = self.rw_info(chan.channel_id)
        event = d.get('sched_next')[idx]
        sched_id = int(event.get('id'))
        sched_type = event.get('type')
        sched_name = event.get('name')
        if sched_type == 'OneUp':
            m = '{} ({} Power Hour):'.format(m, sched_name)
            song = event.get('songs')[0]
            m = '{} {}'.format(m, self.song_string(song))
        elif sched_type == 'Election':
            if sched_name:
                m = '{} ({})'.format(m, sched_name)
            m = '{}:'.format(m)
            for i, s in enumerate(event.get('songs'), start=1):
                song_string = self.song_string(s, simple=True)
                m = '{} \x02[{}]\x02 {}'.format(m, i, song_string)
                req = s.get('elec_request_username')
                if req:
                    m = '{} (requested by {})'.format(m, req)

        if bot.is_irc_channel(target):
            config_id = 'rainwave:nx:{}:{}'.format(chan.channel_id, idx)
            if sched_id == bot.c.get(config_id, 0):
                c = 'You can only use {} in {} once per'.format(cmd, target)
                c = '{} song.'.format(c)
                bot.send_privmsg(sender, c)
                bot.send_privmsg(sender, m)
            else:
                bot.c.set(config_id, sched_id)
                bot.send_privmsg(target, m)
        else:
            bot.send_privmsg(sender, m)


class NowPlayingHandler(RainwaveHandler):
    cmds = ['!nowplaying', '!np', '!npall', '!npbw', '!npch', '!npchip',
            '!npcover', '!npcovers', '!npgame', '!npmw', '!npoc',
            '!npocr', '!npomni', '!npow', '!nprw', '!npvw']
    admin = False
    help_topic = 'nowplaying'
    help_text = [('Use \x02!nowplaying [<channel>]\x02 to show what is now '
                  'playing on the radio.'),
                 'Short version is \x02!np[<channel>]\x02.',
                 RainwaveHandler.channel_codes,
                 ('Leave off <channel> to auto-detect the channel you are '
                  'tuned to.')]

    def handle(self, sender, target, tokens, bot):
        cmd = tokens[0].lower()

        chan = None

        if cmd in ['!npgame', '!nprw']:
            chan = RainwaveChannel.game
        elif cmd in ['!npoc', '!npocr']:
            chan = RainwaveChannel.ocr
        elif cmd in ['!npcover', '!npcovers', '!npmw', '!npvw']:
            chan = RainwaveChannel.cover
        elif cmd in ['!npbw', '!npch', '!npchip']:
            chan = RainwaveChannel.chip
        elif cmd in ['!npall', '!npomni', '!npow']:
            chan = RainwaveChannel.all
        elif cmd in ['!nowplaying', '!np']:
            if len(tokens) > 1:
                if tokens[1].lower() in RainwaveChannel.__members__.keys():
                    chan = RainwaveChannel[tokens[1].lower()]
            if chan is None:
                listener_id = self.get_id_for_nick(sender, bot)
                chan = self.get_current_channel_for_id(listener_id, bot)
            if chan is None:
                m = 'You are not tuned in and you did not specify a valid'
                m = '{} channel code.'.format(m)
                bot.send_privmsg(sender, m)
                return

        m = 'Now playing on the {}'.format(chan.long_name)
        d = self.rw_info(chan.channel_id)
        event = d.get('sched_current')
        sched_id = int(event.get('id'))
        sched_type = event.get('type')
        sched_name = event.get('name')
        if sched_type == 'Election' and sched_name:
            m = '{} ({})'.format(m, sched_name)
        elif sched_type == 'OneUp':
            m = '{} ({} Power Hour)'.format(m, sched_name)
        song = event.get('songs')[0]
        m = '{}: {}'.format(m, self.song_string(song))

        if bot.is_irc_channel(target):
            last = bot.c.get('rainwave:np:{}'.format(chan.channel_id), 0)
            if sched_id == last:
                c = 'You can only use {} in {} once per'.format(cmd, target)
                c = '{} song.'.format(c)
                bot.send_privmsg(sender, c)
                bot.send_privmsg(sender, m)
            else:
                bot.c.set('rainwave:np:{}'.format(chan.channel_id), sched_id)
                bot.send_privmsg(target, m)
        else:
            bot.send_privmsg(sender, m)


class PrevPlayedHandler(RainwaveHandler):
    cmds = ['!prevplayed', '!pp', '!ppall', '!ppbw', '!ppch', '!ppchip',
            '!ppcover', '!ppcovers', '!ppgame', '!ppmw', '!ppoc',
            '!ppocr', '!ppomni', '!ppow', '!pprw', '!ppvw']
    admin = False
    help_topic = 'prevplayed'
    help_text = [('Use \x02!prevplayed [<channel>] [<index>]\x02 to show what '
                  'was previously playing on the radio.'),
                 'Short version is \x02!pp[<channel>] [<index>]\x02.',
                 RainwaveHandler.channel_codes,
                 ('Leave off <channel> to auto-detect the channel you are '
                  'tuned to.'),
                 ('<index> should be a number from 0 to 4. The higher the '
                  'number, the further back in time you go.')]

    def handle(self, sender, target, tokens, bot):
        cmd = tokens[0].lower()

        chan = None
        idx = 0

        if cmd in ['!ppgame', '!pprw']:
            chan = RainwaveChannel.game
        elif cmd in ['!ppoc', '!ppocr']:
            chan = RainwaveChannel.ocr
        elif cmd in ['!ppcover', '!ppcovers', '!ppmw', '!ppvw']:
            chan = RainwaveChannel.cover
        elif cmd in ['!ppbw', '!ppch', '!ppchip']:
            chan = RainwaveChannel.chip
        elif cmd in ['!ppall', '!ppomni', '!ppow']:
            chan = RainwaveChannel.all

        if chan in RainwaveChannel and len(tokens) > 1 and tokens[1].isdigit():
            if int(tokens[1]) in range(5):
                idx = int(tokens[1])

        if cmd in ['!prevplayed', '!pp']:
            if len(tokens) > 1:
                if tokens[1].isdigit() and int(tokens[1]) in range(5):
                    idx = int(tokens[1])
                else:
                    if tokens[1].lower() in RainwaveChannel.__members__.keys():
                        chan = RainwaveChannel[tokens[1].lower()]
                    if len(tokens) > 2:
                        if tokens[2].isdigit() and int(tokens[2]) in range(5):
                            idx = int(tokens[2])
            if chan is None:
                listener_id = self.get_id_for_nick(sender, bot)
                if listener_id is None:
                    bot.send_privmsg(sender, self.NICK_NOT_RECOGNIZED)
                    return
                chan = self.get_current_channel_for_id(listener_id, bot)
            if chan is None:
                m = 'You are not tuned in and you did not specify a channel'
                m = '{} code.'.format(m)
                bot.send_privmsg(sender, m)
                return

        m = 'Previously on the {}'.format(chan.long_name)
        d = self.rw_info(chan.channel_id)
        event = d.get('sched_history')[idx]
        sched_id = int(event.get('id'))
        sched_type = event.get('type')
        sched_name = event.get('name')
        if sched_type == 'Election' and sched_name:
            m = '{} ({})'.format(m, sched_name)
        elif sched_type == 'OneUp':
            m = '{} ({} Power Hour)'.format(m, sched_name)
        song = event.get('songs')[0]
        m = '{}: {}'.format(m, self.song_string(song))

        if bot.is_irc_channel(target):
            last_sched_id = 'rainwave:pp:{}:{}'.format(chan.channel_id, idx)
            if sched_id == bot.c.get(last_sched_id, 0):
                c = 'You can only use {} in {} once per'.format(cmd, target)
                c = '{} song.'.format(c)
                bot.send_privmsg(sender, c)
                bot.send_privmsg(sender, m)
            else:
                bot.c.set(last_sched_id, sched_id)
                bot.send_privmsg(target, m)
        else:
            bot.send_privmsg(sender, m)


class RequestHandler(RainwaveHandler):
    cmds = ['!rq']
    admin = False
    help_topic = 'request'
    help_text = [('Use \x02!rq <song_id>\x02 to add a song to your request '
                  'queue.'),
                 ('Use \x02!rq unrated\x02 to fill your request queue with '
                  'unrated songs.'),
                 ('Use \x02!rq fav\x02 to add favourite songs to your request '
                  'queue.'),
                 'Use \x02!rq pause\x02 to pause your request queue.',
                 'Use \x02!rq resume\x02 to resume your request queue.',
                 ('Use \x02!rq clear\x02 to remove all songs from your '
                  'request queue.')]

    def handle(self, sender, _, tokens, bot):
        if len(tokens) < 2:
            self.send_help(sender, bot)
            return

        auth = self.get_api_auth_for_nick(sender, bot)
        if auth.get('user_id') is None:
            bot.send_privmsg(sender, self.NICK_NOT_RECOGNIZED)
            return
        if auth.get('key') is None:
            bot.send_privmsg(sender, self.MISSING_KEY)
            return
        if auth.get('chan') is None:
            bot.send_privmsg(sender, 'You must be tuned in to request.')
            return

        if tokens[1].isdigit():
            song_id = int(tokens[1])
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = self.rw_song(user_id, key, chan_id, song_id)
            song = d.get('song')
            song_str = self.song_string(song, simple=True)
            bot.send_privmsg(sender, 'Attempting request: {}'.format(song_str))
            d = self.rw_request(user_id, key, chan_id, song_id)
            bot.send_privmsg(sender, d.get('request_result').get('text'))

        elif tokens[1] == 'unrated':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = self.rw_request_unrated_songs(user_id, key, chan_id)
            m = d.get('request_unrated_songs_result').get('text')
            bot.send_privmsg(sender, m)

        elif tokens[1] == 'fav':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = self.rw_request_favorited_songs(user_id, key, chan_id)
            m = d.get('request_favorited_songs_result').get('text')
            bot.send_privmsg(sender, m)

        elif tokens[1] == 'clear':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            _ = self.rw_clear_requests(user_id, key, chan_id)
            bot.send_privmsg(sender, 'Request queue cleared.')

        elif tokens[1] == 'pause':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = self.rw_pause_request_queue(user_id, key, chan_id)
            m = d.get('pause_request_queue_result').get('text')
            bot.send_privmsg(sender, m)

        elif tokens[1] == 'resume':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = self.rw_unpause_request_queue(user_id, key, chan_id)
            m = d.get('unpause_request_queue_result').get('text')
            bot.send_privmsg(sender, m)


class UserStatsHandler(RainwaveHandler):
    cmds = ['!ustats']
    admin = False
    help_topic = 'ustats'
    help_text = [('Use \x02!ustats [<username>]\x02 to see some statistics '
                  'about a Rainwave user.'),
                 'Leave off <username> to see your own stats.']

    def handle(self, sender, target, tokens, bot):
        out = list()

        if len(tokens) > 1:
            uname = tokens[1]
        else:
            uname = sender

        auth = self.get_api_auth_for_nick(uname, bot)
        if auth.get('user_id') is None:
            m = '{} is not a valid Rainwave user.'.format(uname)
            bot.send_privmsg(sender, m)
            return

        user_id = bot.c.get('rainwave:user_id')
        key = bot.c.get('rainwave:key')
        d = self.rw_listener(user_id, key, auth.get('user_id'))
        cun = d.get('listener').get('name')
        completion = d.get('listener').get('rating_completion')
        game = int(completion.get('1', 0))
        ocr = int(completion.get('2', 0))
        cover = int(completion.get('3', 0))
        chip = int(completion.get('4', 0))
        m = '{} has rated {}% of Game, {}% of OCR,'.format(cun, game, ocr)
        m = '{} {}% of Covers, {}% of Chiptune'.format(m, cover, chip)
        m = '{} channel content.'.format(m)
        out.append(m)

        if auth.get('chan'):
            chan_name = auth.get('chan').long_name
            m = '{} is currently listening to the {}.'.format(cun, chan_name)
            out.append(m)

        if not bot.is_irc_channel(target):
            for line in out:
                bot.send_privmsg(sender, line)
            return

        now = int(time.time())
        last = int(bot.c.get('rainwave:ustats:last', 0))
        wait = int(bot.c.get('rainwave:ustats:wait', 0))
        if last < now - wait:
            for line in out:
                bot.send_privmsg(target, line)
            bot.c.set('rainwave:ustats:last', now)
        else:
            for line in out:
                bot.send_privmsg(sender, line)
            remaining = last + wait - now
            m = 'I am cooling down. You cannot use {}'.format(tokens[0])
            m = '{} in {} for another'.format(m, target)
            m = '{} {} seconds.'.format(m, remaining)
            bot.send_privmsg(sender, m)


class VoteHandler(RainwaveHandler):
    cmds = ['!vote', '!vt']
    admin = False
    help_topic = 'vote'
    help_text = [('Use \x02!vote <index>\x02 to vote in the current election, '
                  'find the <index> with \x02!next\x02.')]

    def handle(self, sender, _, tokens, bot):
        if len(tokens) > 1:
            idx = tokens[1]
        else:
            m = 'You did not tell me which song you wanted to vote for.'
            bot.send_privmsg(sender, m)
            return

        if idx.isdigit():
            idx = int(idx)
        else:
            m = '{} is not a valid voting option.'.format(idx)
            bot.send_privmsg(sender, m)
            return

        auth = self.get_api_auth_for_nick(sender, bot)
        if auth.get('user_id') is None:
            bot.send_privmsg(sender, self.NICK_NOT_RECOGNIZED)
            return
        if auth.get('key') is None:
            bot.send_privmsg(sender, self.MISSING_KEY)
            return
        if auth.get('chan') is None:
            bot.send_privmsg(sender, 'You must be tuned in to vote.')
            return

        chan = auth.get('chan')
        d = self.rw_info(chan.channel_id)
        event = d.get('sched_next')[0]
        sched_type = event.get('type')

        if sched_type == 'OneUp':
            bot.send_privmsg(sender, 'You cannot vote during a Power Hour.')
            return

        if idx < 1 or idx > len(event.get('songs')):
            m = '{} is not a valid voting option'.format(idx)
            bot.send_privmsg(sender, m)
            return

        song = event.get('songs')[idx - 1]
        elec_entry_id = song.get('entry_id')
        user_id = auth.get('user_id')
        key = auth.get('key')
        d = self.rw_vote(user_id, key, chan.channel_id, elec_entry_id)
        if d.get('vote_result').get('success'):
            song_string = self.song_string(song, simple=True)
            m = 'You successfully voted for {}'.format(song_string)
            bot.send_privmsg(sender, m)
        else:
            m = 'Your attempt to vote was not successful.'
            bot.send_privmsg(sender, m)
