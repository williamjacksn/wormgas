import requests
import time

chan_code_to_id = {
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

chan_id_to_name = [
    u'Rainwave network',
    u'Game channel',
    u'OCR channel',
    u'Covers channel',
    u'Chiptune channel',
    u'All channel'
]

NICK_NOT_RECOGNIZED = (u'I do not recognize you. If your nick does not match '
                       u'your Rainwave username, use \x02!id\x02 to link your '
                       u'Rainwave account to your nick.')

MISSING_KEY = (u'I do not have a key stored for you. Visit '
               u'http://rainwave.cc/keys/ to get a key and tell me about it '
               u'with \x02!key add <key>\x02.')


def get_api_auth_for_nick(nick, config):
    auth = dict()
    auth[u'user_id'] = get_id_for_nick(nick, config)
    auth[u'key'] = config.get_key_for_nick(nick)
    auth[u'chan_id'] = get_current_channel_for_id(auth.get(u'user_id'), config)
    return auth


def get_current_channel_for_id(listener_id, config):
    if listener_id is None:
        return None
    user_id = config.get(u'rw:user_id')
    key = config.get(u'rw:key')
    d = rw_listener(user_id, key, listener_id)
    listener_name = d.get(u'listener').get(u'name')
    return get_current_channel_for_name(listener_name, config)


def get_current_channel_for_name(name, config):
    user_id = config.get(u'rw:user_id')
    key = config.get(u'rw:key')
    d = rw_user_search(user_id, key, name)
    return d.get(u'user').get(u'sid')


def get_id_for_nick(nick, config):
    listener_id = config.get_id_for_nick(nick)
    if listener_id is None:
        user_id = config.get(u'rw:user_id')
        key = config.get(u'rw:key')
        d = rw_user_search(user_id, key, nick)
        listener_id = d.get(u'user').get(u'user_id')
    return listener_id


def _call(path, params=None):
    if params is None:
        params = dict()
    base_url = u'http://rainwave.cc/api4/'
    url = u'{}{}'.format(base_url, path.lstrip(u'/'))
    d = requests.post(url, params=params)
    if d.ok:
        return d.json()
    d.raise_for_status()


def rw_current_listeners(user_id, key, sid):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid
    }
    return _call(u'current_listeners', params=params)


def rw_info(sid):
    params = {u'sid': sid}
    return _call(u'info', params=params)


def rw_listener(user_id, key, listener_id):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'id': listener_id
    }
    return _call(u'listener', params=params)


def rw_request(user_id, key, sid, song_id):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid,
        u'song_id': song_id
    }
    return _call(u'request', params=params)


def rw_clear_requests(user_id, key, sid):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid
    }
    return _call(u'clear_requests', params=params)


def rw_request_favorited_songs(user_id, key, sid):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid
    }
    return _call(u'request_favorited_songs', params=params)


def rw_request_unrated_songs(user_id, key, sid):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid
    }
    return _call(u'request_unrated_songs', params=params)


def rw_pause_request_queue(user_id, key, sid):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid
    }
    return _call(u'pause_request_queue', params=params)


def rw_unpause_request_queue(user_id, key, sid):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid
    }
    return _call(u'unpause_request_queue', params=params)


def rw_song(user_id, key, sid, song_id):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid,
        u'id': song_id
    }
    return _call(u'song', params=params)


def rw_user_search(user_id, key, username):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'username': username
    }
    return _call(u'user_search', params=params)


def rw_vote(user_id, key, sid, entry_id):
    params = {
        u'user_id': user_id,
        u'key': key,
        u'sid': sid,
        u'entry_id': entry_id
    }
    return _call(u'vote', params=params)


def is_irc_channel(s):
    return s and s[0] == u'#'


def artist_string(artists):
    return u', '.join([a.get(u'name') for a in artists])


def build_song_info_string(song, simple=False):
    m = u'{} //'.format(song.get(u'albums')[0].get(u'name'))
    artists = artist_string(song.get(u'artists'))
    m = u'{} {} // {}'.format(m, song.get(u'title'), artists)

    if simple:
        return m

    url = song.get(u'url')
    if url is not None:
        m = u'{} [ {} ]'.format(m, url)

    vote_count = song.get(u'entry_votes', 0)
    m = u'{} ({} vote'.format(m, vote_count)
    if int(vote_count) != 1:
        m = u'{}s'.format(m)

    m = u'{}, rated {}'.format(m, song.get(u'rating'))

    elec_request_username = song.get(u'elec_request_username')
    if elec_request_username is not None:
        m = u'{}, requested by {}'.format(m, elec_request_username)

    m = u'{})'.format(m)

    return m


class ListenerStatsHandler(object):
    cmds = [u'!lstats']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        m = u'Registered listeners: '
        total = 0
        user_id = config.get(u'rw:user_id')
        key = config.get(u'rw:key')
        for chan_id in range(1, 6):
            d = rw_current_listeners(user_id, key, chan_id)
            count = len(d.get(u'current_listeners'))
            m = u'{}{} = {}, '.format(m, chan_id_to_name[chan_id], count)
            total = total + count
        m = u'{}Total = {}'.format(m, total)

        if not is_irc_channel(target):
            private.append(m)
            return public, private

        now = int(time.time())
        last = int(config.get(u'lstats:last', 0))
        wait = int(config.get(u'lstats:wait', 0))
        if last < now - wait:
            public.append(m)
            config.set(u'lstats:last', now)
        else:
            private.append(m)
            remaining = last + wait - now
            m = u'I am cooling down. You cannot use {}'.format(tokens[0])
            m = u'{} in {} for another'.format(m, target)
            m = u'{} {} seconds.'.format(m, remaining)
            private.append(m)

        return public, private


class NextHandler(object):
    cmds = [u'!next', u'!nx', u'!nxall', u'!nxbw', u'!nxch', u'!nxchip',
            u'!nxcover', u'!nxcovers', u'!nxgame', u'!nxmw', u'!nxoc',
            u'!nxocr', u'!nxomni', u'!nxow', u'!nxrw', u'!nxvw']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        cmd = tokens[0].lower()

        chan_id = None
        idx = 0

        if cmd in [u'!nxgame', u'!nxrw']:
            chan_id = 1

        if cmd in [u'!nxoc', u'!nxocr']:
            chan_id = 2

        if cmd in [u'!nxcover', u'!nxcovers', u'!nxmw', u'!nxvw']:
            chan_id = 3

        if cmd in [u'!nxbw', u'!nxch', u'!nxchip']:
            chan_id = 4

        if cmd in [u'!nxall', u'!nxomni', u'!nxow']:
            chan_id = 5

        if cmd in [u'!next', u'!nx']:
            if len(tokens) > 1:
                chan_id = chan_code_to_id.get(tokens[1].lower())
            if chan_id is None:
                listener_id = get_id_for_nick(sender, config)
                chan_id = get_current_channel_for_id(listener_id, config)
            if chan_id is None:
                m = u'You are not tuned in and you did not specify a valid'
                m = u'{} channel code.'.format(m)
                private.append(m)
                return public, private

        m = u'Next up on the {}'.format(chan_id_to_name[int(chan_id)])
        d = rw_info(chan_id)
        event = d.get(u'sched_next')[idx]
        sched_id = int(event.get(u'id'))
        sched_type = event.get(u'type')
        sched_name = event.get(u'name')
        if sched_type == u'OneUp':
            m = u'{} ({} Power Hour):'.format(m, sched_name)
            song = event.get(u'songs')[0]
            m = u'{} {}'.format(m, build_song_info_string(song))
        elif sched_type == u'Election':
            if sched_name:
                m = u'{} ({})'.format(m, sched_name)
            m = u'{}:'.format(m)
            for i, s in enumerate(event.get(u'songs'), start=1):
                song_string = build_song_info_string(s, simple=True)
                m = u'{} \x02[{}]\x02 {}'.format(m, i, song_string)
                req = s.get(u'elec_request_username')
                if req:
                    m = u'{} (requested by {})'.format(m, req)

        if is_irc_channel(target):
            if sched_id == config.get(u'nx:{}:{}'.format(chan_id, idx), 0):
                c = u'You can only use {} in {} once per'.format(cmd, target)
                c = u'{} song.'.format(c)
                private.append(c)
                private.append(m)
            else:
                config.set(u'nx:{}:{}'.format(chan_id, idx), sched_id)
                public.append(m)
        else:
            private.append(m)

        return public, private


class NowPlayingHandler(object):
    cmds = [u'!nowplaying', u'!np', u'!npall', u'!npbw', u'!npch', u'!npchip',
            u'!npcover', u'!npcovers', u'!npgame', u'!npmw', u'!npoc',
            u'!npocr', u'!npomni', u'!npow', u'!nprw', u'!npvw']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        cmd = tokens[0].lower()

        chan_id = None

        if cmd in [u'!npgame', u'!nprw']:
            chan_id = 1

        if cmd in [u'!npoc', u'!npocr']:
            chan_id = 2

        if cmd in [u'!npcover', u'!npcovers', u'!npmw', u'!npvw']:
            chan_id = 3

        if cmd in [u'!npbw', u'!npch', u'!npchip']:
            chan_id = 4

        if cmd in [u'!npall', u'!npomni', u'!npow']:
            chan_id = 5

        if cmd in [u'!nowplaying', u'!np']:
            if len(tokens) > 1:
                chan_id = chan_code_to_id.get(tokens[1].lower())
            if chan_id is None:
                listener_id = get_id_for_nick(sender, config)
                chan_id = get_current_channel_for_id(listener_id, config)
            if chan_id is None:
                m = u'You are not tuned in and you did not specify a valid'
                m = u'{} channel code.'.format(m)
                private.append(m)
                return public, private

        m = u'Now playing on the {}'.format(chan_id_to_name[int(chan_id)])
        d = rw_info(chan_id)
        event = d.get(u'sched_current')
        sched_id = int(event.get(u'id'))
        sched_type = event.get(u'type')
        sched_name = event.get(u'name')
        if sched_type == u'Election' and sched_name:
            m = u'{} ({})'.format(m, sched_name)
        elif sched_type == u'OneUp':
            m = u'{} ({} Power Hour)'.format(m, sched_name)
        song = event.get(u'songs')[0]
        m = u'{}: {}'.format(m, build_song_info_string(song))

        if is_irc_channel(target):
            if sched_id == config.get(u'np:{}'.format(chan_id), 0):
                c = u'You can only use {} in {} once per'.format(cmd, target)
                c = u'{} song.'.format(c)
                private.append(c)
                private.append(m)
            else:
                config.set(u'np:{}'.format(chan_id), sched_id)
                public.append(m)
        else:
            private.append(m)

        return public, private


class PrevPlayedHandler(object):
    cmds = [u'!prevplayed', u'!pp', u'!ppall', u'!ppbw', u'!ppch', u'!ppchip',
            u'!ppcover', u'!ppcovers', u'!ppgame', u'!ppmw', u'!ppoc',
            u'!ppocr', u'!ppomni', u'!ppow', u'!pprw', u'!ppvw']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        cmd = tokens[0].lower()

        chan_id = None
        idx = 0

        if cmd in [u'!ppgame', u'!pprw']:
            chan_id = 1

        if cmd in [u'!ppoc', u'!ppocr']:
            chan_id = 2

        if cmd in [u'!ppcover', u'!ppcovers', u'!ppmw', u'!ppvw']:
            chan_id = 3

        if cmd in [u'!ppbw', u'!ppch', u'!ppchip']:
            chan_id = 4

        if cmd in [u'!ppall', u'!ppomni', u'!ppow']:
            chan_id = 5

        if chan_id in range(1, 6) and len(tokens) > 1 and tokens[1].isdigit():
            if int(tokens[1]) in range(5):
                idx = int(tokens[1])

        if cmd in [u'!prevplayed', u'!pp']:
            if len(tokens) > 1:
                if tokens[1].isdigit() and int(tokens[1]) in range(5):
                    idx = int(tokens[1])
                else:
                    chan_id = chan_code_to_id.get(tokens[1].lower())
                    if len(tokens) > 2 and int(tokens[2]) in range(5):
                        idx = int(tokens[2])
            if chan_id is None:
                listener_id = get_id_for_nick(sender, config)
                if listener_id is None:
                    private.append(NICK_NOT_RECOGNIZED)
                    return public, private
                chan_id = get_current_channel_for_id(listener_id, config)
            if chan_id is None:
                m = u'You are not tuned in and you did not specify a channel'
                m = u'{} code.'.format(m)
                private.append(m)
                return public, private

        m = u'Previously on the {}'.format(chan_id_to_name[int(chan_id)])
        d = rw_info(chan_id)
        event = d.get(u'sched_history')[idx]
        sched_id = int(event.get(u'id'))
        sched_type = event.get(u'type')
        sched_name = event.get(u'name')
        if sched_type == u'Election' and sched_name:
            m = u'{} ({})'.format(m, sched_name)
        elif sched_type == u'OneUp':
            m = u'{} ({} Power Hour)'.format(m, sched_name)
        song = event.get(u'songs')[0]
        m = u'{}: {}'.format(m, build_song_info_string(song))

        if is_irc_channel(target):
            if sched_id == config.get(u'pp:{}:{}'.format(chan_id, idx), 0):
                c = u'You can only use {} in {} once per'.format(cmd, target)
                c = u'{} song.'.format(c)
                private.append(c)
                private.append(m)
            else:
                config.set(u'pp:{}:{}'.format(chan_id, idx), sched_id)
                public.append(m)
        else:
            private.append(m)

        return public, private


class RequestHandler(object):
    cmds = [u'!rq']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        cmd = tokens[0].lower()

        if len(tokens) < 2:
            private.append(u'You didn\'t specify an argument.')
            return public, private

        auth = get_api_auth_for_nick(sender, config)
        if auth.get(u'user_id') is None:
            private.append(NICK_NOT_RECOGNIZED)
            return public, private
        if auth.get(u'key') is None:
            private.append(MISSING_KEY)
            return public, private
        if auth.get(u'chan_id') is None:
            private.append(u'You must be tuned in to request.')
            return public, private

        if tokens[1].isdigit():
            song_id = int(tokens[1])
            user_id = auth.get(u'user_id')
            key = auth.get(u'key')
            d = rw_song(user_id, key, auth.get(u'chan_id'), song_id)
            song = d.get(u'song')
            song_str = build_song_info_string(song, simple=True)
            private.append(u'Attempting request: {}'.format(song_str))
            d = rw_request(user_id, key, auth.get(u'chan_id'), song_id)
            private.append(d.get(u'request_result').get(u'text'))

        elif tokens[1] == u'unrated':
            user_id = auth.get(u'user_id')
            key = auth.get(u'key')
            chan_id = auth.get(u'chan_id')
            d = rw_request_unrated_songs(user_id, key, chan_id)
            private.append(d.get(u'request_unrated_songs_result').get(u'text'))

        elif tokens[1] == u'fav':
            user_id = auth.get(u'user_id')
            key = auth.get(u'key')
            chan_id = auth.get(u'chan_id')
            d = rw_request_favorited_songs(user_id, key, chan_id)
            m = d.get(u'request_favorited_songs_result').get(u'text')
            private.append(m)

        elif tokens[1] == u'clear':
            user_id = auth.get(u'user_id')
            key = auth.get(u'key')
            chan_id = auth.get(u'chan_id')
            d = rw_clear_requests(user_id, key, chan_id)
            private.append(u'Request queue cleared.')

        elif tokens[1] == u'pause':
            user_id = auth.get(u'user_id')
            key = auth.get(u'key')
            chan_id = auth.get(u'chan_id')
            d = rw_pause_request_queue(user_id, key, chan_id)
            m = d.get(u'pause_request_queue_result').get(u'text')
            private.append(m)

        elif tokens[1] == u'resume':
            user_id = auth.get(u'user_id')
            key = auth.get(u'key')
            chan_id = auth.get(u'chan_id')
            d = rw_unpause_request_queue(user_id, key, chan_id)
            m = d.get(u'unpause_request_queue_result').get(u'text')
            private.append(m)

        return public, private


class UserStatsHandler(object):
    cmds = [u'!ustats']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()
        out = list()

        if len(tokens) > 1:
            uname = tokens[1]
        else:
            uname = sender

        auth = get_api_auth_for_nick(uname, config)
        if auth.get(u'user_id') is None:
            private.append(u'{} is not a valid Rainwave user.'.format(uname))
            return public, private

        user_id = config.get(u'rw:user_id')
        d = rw_listener(user_id, config.get(u'rw:key'), auth.get(u'user_id'))
        cun = d.get(u'listener').get(u'name')
        completion = d.get(u'listener').get(u'rating_completion')
        game = int(completion.get(u'1'))
        ocr = int(completion.get(u'2'))
        cover = int(completion.get(u'3'))
        chip = int(completion.get(u'4'))
        m = u'{} has rated {}% of Game, {}% of OCR,'.format(cun, game, ocr)
        m = u'{} {}% of Covers, {}% of Chiptune'.format(m, cover, chip)
        m = u'{} channel content.'.format(m)
        out.append(m)

        if auth.get(u'chan_id'):
            chan_name = chan_id_to_name[auth.get(u'chan_id')]
            m = u'{} is currently listening to the {}.'.format(cun, chan_name)
            out.append(m)

        if not is_irc_channel(target):
            private.extend(out)
            return public, private

        now = int(time.time())
        last = int(config.get(u'ustats:last', 0))
        wait = int(config.get(u'ustats:wait', 0))
        if last < now - wait:
            public.extend(out)
            config.set(u'ustats:last', now)
        else:
            private.extend(out)
            remaining = last + wait - now
            m = u'I am cooling down. You cannot use {}'.format(tokens[0])
            m = u'{} in {} for another'.format(m, target)
            m = u'{} {} seconds.'.format(m, remaining)
            private.append(m)

        return public, private


class VoteHandler(object):
    cmds = [u'!vote', u'!vt']
    admin = False

    @classmethod
    def handle(cls, sender, target, tokens, config):
        public = list()
        private = list()

        if len(tokens) > 1:
            idx = tokens[1]
        else:
            m = u'You did not tell me which song you wanted to vote for.'
            private.append(m)
            return public, private

        if idx.isdigit():
            idx = int(idx)
        else:
            private.append(u'{} is not a valid voting option.'.format(idx))
            return public, private

        auth = get_api_auth_for_nick(sender, config)
        if auth.get(u'user_id') is None:
            private.append(NICK_NOT_RECOGNIZED)
            return public, private
        if auth.get(u'key') is None:
            private.append(MISSING_KEY)
            return public, private
        if auth.get(u'chan_id') is None:
            private.append(u'You must be tuned in to vote.')
            return public, private

        d = rw_info(auth.get(u'chan_id'))
        event = d.get(u'sched_next')[0]
        sched_id = int(event.get(u'id'))
        sched_type = event.get(u'type')

        if sched_type == u'OneUp':
            private.append(u'You cannot vote during a Power Hour.')
            return public, private

        if idx < 1 or idx > len(event.get(u'songs')):
            private.append(u'{} is not a valid voting option'.format(idx))
            return public, private

        song = event.get(u'songs')[idx - 1]
        elec_entry_id = song.get(u'entry_id')
        user_id = auth.get(u'user_id')
        key = auth.get(u'key')
        d = rw_vote(user_id, key, auth.get(u'chan_id'), elec_entry_id)
        if d.get(u'vote_result').get(u'success'):
            song_string = build_song_info_string(song, simple=True)
            m = u'You successfully voted for {}'.format(song_string)
            private.append(m)
        else:
            private.append(u'Your attempt to vote was not successful.')

        return public, private
