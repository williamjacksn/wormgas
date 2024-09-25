import datetime
import discord
import enum
import logging
import time
import uuid
import zoneinfo

from discord.ext import commands, tasks
from wormgas.util import to_bool
from wormgas.wormgas import Wormgas

log = logging.getLogger(__name__)


class RainwaveChannel(enum.Enum):
    game = 1
    rw = 1
    oc = 2
    ocr = 2
    ocremix = 3
    cover = 3
    covers = 3
    mw = 3
    vw = 3
    bw = 4
    ch = 4
    chip = 4
    chiptune = 4
    all = 5
    omni = 5
    ow = 5

    @property
    def channel_id(self):
        return self.value

    @property
    def long_name(self):
        return f'{self.short_name} channel'

    @property
    def short_name(self):
        return (None, 'Game', 'OCR', 'Covers', 'Chiptune', 'All')[int(self.value)]

    @property
    def url(self):
        return 'https://rainwave.cc/' + ('', 'game/', 'ocremix/', 'covers/', 'chiptune/', 'all/')[int(self.value)]

    @property
    def voice_channel_name(self):
        return (None, 'game', 'ocremix', 'covers', 'chiptune', 'all')[int(self.value)]

class RainwaveCog(commands.Cog):
    def __init__(self, bot: Wormgas):
        self.bot = bot
        self.nick_not_recognized = ('I do not recognize you. Use **!id add <id>** to link your Rainwave and Discord '
                                    'accounts.')
        self.missing_key = ('I do not have a key stored for you. Visit https://rainwave.cc/keys/ to get a key and tell '
                            'me about it with **!key add <key>**.')
        self.not_tuned_in = 'You are not tuned in and you did not specify a valid channel code.'
        codes = [code for code in RainwaveChannel.__members__.keys()]
        chan_code_ls = '**, **'.join(codes)
        self.channel_codes = f'Channel codes are **{chan_code_ls}**.'
        self.sync_events.start()

    async def _call(self, path: str, params: dict = None):
        log.debug(f'_call {path} {params}')
        if params is None:
            params = {}
        base_url = 'https://rainwave.cc/api4/'
        url = base_url + path.lstrip('/')
        headers = {'user-agent': str(uuid.uuid4())}
        async with self.bot.session.post(url, params=params, headers=headers) as response:
            content = await response.text()
            log.debug(f'{response.status} {content}')
            if response.status == 200:
                return await response.json()
        raise RuntimeError

    @staticmethod
    def artist_string(artists):
        return ', '.join([a.get('name') for a in artists])

    def song_string(self, song, simple=False):
        album = song.get("albums")[0].get("name")
        title = song.get('title')
        artists = self.artist_string(song.get('artists'))
        m = f'{album} // {title} // {artists}'

        if simple:
            return m

        url = song.get('url')
        if url is not None:
            m += f' [ {url} ]'

        vote_count = song.get('entry_votes', 0)
        vote_plural = 's'
        if int(vote_count) == 1:
            vote_plural = ''
        rating = song.get('rating')
        m += f' ({vote_count} vote{vote_plural}, rated {rating}'

        elec_request_username = song.get('elec_request_username')
        if elec_request_username is not None:
            m += f', requested by {elec_request_username}'

        m += ')'
        return m

    async def get_api_auth_for_user(self, user: discord.User) -> dict:
        return {
            'user_id': await self.get_id_for_user(user),
            'key': await self.get_key_for_user(user),
            'chan': await self.get_current_channel_for_user(user)
        }

    async def get_current_channel_for_name(self, name: str):
        user_id = self.bot.db.config_get('rainwave:user_id')
        key = self.bot.db.config_get('rainwave:key')
        d = await self.rw_user_search(user_id, key, name)
        chan_id = d.get('user').get('sid')
        if chan_id is None:
            return None
        return RainwaveChannel(int(chan_id))

    async def get_current_channel_for_user(self, user: discord.User) -> RainwaveChannel:
        user_info = await self.rw_user_search_by_discord_user_id(str(user.id))
        user_sid = user_info.get('user', {}).get('sid')
        if user_sid:
            return RainwaveChannel(user_sid)
        if hasattr(user, 'voice') and user.voice:
            vc_name = user.voice.channel.name
            if vc_name.lower() in RainwaveChannel.__members__.keys():
                return RainwaveChannel[vc_name.lower()]

    async def get_id_for_name(self, username: str):
        rw_user_id = self.bot.db.config_get('rainwave:user_id')
        key = self.bot.db.config_get('rainwave:key')
        d = await self.rw_user_search(rw_user_id, key, username)
        return d.get('user').get('user_id')

    async def get_id_for_user(self, user: discord.User):
        user_id = str(user.id)
        user_info = await self.rw_user_search_by_discord_user_id(user_id)
        return user_info.get('user', {}).get('user_id')

    async def get_key_for_user(self, user: discord.User):
        return self.bot.db.rw_api_keys_get(user.id)

    async def rw_admin_list_producers_all(self, user_id, key):
        params = {
            'user_id': user_id,
            'key': key
        }
        return await self._call('admin/list_producers_all', params=params)

    async def rw_clear_requests(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return await self._call('clear_requests', params=params)

    async def rw_current_listeners(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return await self._call('current_listeners', params=params)

    async def rw_info(self, sid):
        params = {'sid': sid}
        return await self._call('info', params=params)

    async def rw_listener(self, user_id, key, listener_id):
        params = {
            'user_id': user_id,
            'key': key,
            'id': listener_id
        }
        return await self._call('listener', params=params)

    async def rw_pause_request_queue(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return await self._call('pause_request_queue', params=params)

    async def rw_request(self, user_id, key, sid, song_id):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid,
            'song_id': song_id
        }
        return await self._call('request', params=params)

    async def rw_request_favorited_songs(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return await self._call('request_favorited_songs', params=params)

    async def rw_request_unrated_songs(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return await self._call('request_unrated_songs', params=params)

    async def rw_song(self, user_id, key, sid, song_id):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid,
            'id': song_id
        }
        return await self._call('song', params=params)

    async def rw_unpause_request_queue(self, user_id, key, sid):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid
        }
        return await self._call('unpause_request_queue', params=params)

    async def rw_user_search(self, user_id, key, username):
        params = {
            'user_id': user_id,
            'key': key,
            'username': username
        }
        return await self._call('user_search', params=params)

    async def rw_user_search_by_discord_user_id(self, discord_user_id: str):
        params = {
            'discord_user_id': discord_user_id,
        }
        return await self._call('user_search_by_discord_user_id', params=params)

    async def rw_vote(self, user_id, key, sid, entry_id):
        params = {
            'user_id': user_id,
            'key': key,
            'sid': sid,
            'entry_id': entry_id
        }
        return await self._call('vote', params=params)

    async def rw_update_nickname(self, discord_user_id, nickname):
        params = {
            'discord_user_id': discord_user_id,
            'nickname': nickname,
        }
        return await self._call('update_user_nickname_by_discord_id', params=params)

    async def rw_update_avatar(self, discord_user_id: int, avatar: discord.Asset):
        params = {
            'discord_user_id': discord_user_id,
            'avatar': avatar.url,
        }
        return await self._call('update_user_avatar_by_discord_id', params=params)

    async def rw_enable_perks(self, discord_users: list[discord.Member]):
        params = {
            'discord_user_ids': ','.join([str(u.id) for u in discord_users]),
        }
        return await self._call('enable_perks_by_discord_ids', params=params)

    @tasks.loop(minutes=1)
    async def sync_events(self):
        await self.bot.wait_until_ready()
        log.info('Syncing Rainwave events with Discord')
        user_id = self.bot.db.config_get('rainwave:user_id')
        key = self.bot.db.config_get('rainwave:key')
        d = await self.rw_admin_list_producers_all(user_id=user_id, key=key)
        for p in d.get('producers', []):
            p_id = p.get('id')
            local_record = self.bot.db.events_get(p_id)
            if local_record is not None:
                log.debug('This event is already known')
                continue
            name = p.get('name')
            eastern = zoneinfo.ZoneInfo('America/New_York')
            e_start = p.get('start')
            start_time = datetime.datetime.fromtimestamp(e_start, eastern)
            e_end = p.get('end')
            end_time = datetime.datetime.fromtimestamp(e_end, eastern)
            sid = p.get('sid')
            rw_channel = RainwaveChannel(sid)
            if p.get('type') == 'PVPElectionProducer':
                desc = f'Listener requests compete head-to-head in PvP elections on the {rw_channel.short_name} channel'
            else:
                desc = f'Join us for this Power Hour on the {rw_channel.short_name} channel'
            reason = f'Rainwave event id: {p_id}'
            for g in self.bot.guilds:
                channel = None
                for vc in g.voice_channels:
                    if vc.name == rw_channel.voice_channel_name:
                        channel = vc
                        break
                log.debug('Creating a new event in Discord')
                event = await g.create_scheduled_event(
                    name=name, description=desc, channel=channel, start_time=start_time, end_time=end_time,
                    privacy_level=discord.PrivacyLevel.guild_only, reason=reason)
                self.bot.db.events_insert(p_id, event.id)

    @commands.group()
    async def key(self, ctx: commands.Context):
        """Manage your Rainwave key"""

    @key.command(name='add')
    async def key_add(self, ctx: commands.Context, rainwave_key: str):
        """Add your Rainwave key to your Discord account."""
        self.bot.db.rw_api_keys_set(ctx.author.id, rainwave_key)
        await ctx.author.send(f'I assigned the key {rainwave_key} to {ctx.author.mention}.')

    @key.command(name='drop')
    async def key_drop(self, ctx: commands.Context):
        """Drop your Rainwave key from your Discord account."""
        self.bot.db.rw_api_keys_delete(ctx.author.id)
        await ctx.author.send(f'I dropped the key for {ctx.author.mention}')

    @key.command(name='show')
    async def key_show(self, ctx: commands.Context):
        """See the Rainwave key associated with your Discord account."""
        rw_api_key = self.bot.db.rw_api_keys_get(ctx.author.id)
        if rw_api_key:
            await ctx.author.send(f'The key for {ctx.author.mention} is {rw_api_key}.')
        else:
            await ctx.author.send(f'I do not have a key for {ctx.author.mention}')

    @commands.command()
    async def lstats(self, ctx: commands.Context):
        """See information about current Rainwave radio listeners."""
        m = 'Registered listeners: '
        total = 0
        user_id = self.bot.db.config_get('rainwave:user_id')
        key = self.bot.db.config_get('rainwave:key')
        for chan in RainwaveChannel:
            d = await self.rw_current_listeners(user_id, key, chan.channel_id)
            count = len(d.get('current_listeners'))
            m += f'{chan.long_name} = {count}, '
            total += count
        m += f'Total = {total}'
        await ctx.send(m)

    @staticmethod
    def build_embed(song: dict):
        channel = RainwaveChannel(song['sid'])
        album_name = song['albums'][0]['name']
        album_id = song['albums'][0]['id']
        album_url = channel.url + f'#!/album/{album_id}'
        artist_links = []
        for artist in song['artists']:
            artist_name = artist['name']
            artist_id = artist['id']
            artist_links.append(f'[{artist_name}]({channel.url}#!/artist/{artist_id})')
        artists = ', '.join(artist_links)
        description = f'from [{album_name}]({album_url})\nby {artists}'
        embed = discord.Embed(title=song['title'], colour=discord.Colour(0xf7941e), description=description)
        album_art = song['albums'][0]['art']
        embed.set_thumbnail(url=f'https://rainwave.cc{album_art}_320.jpg')
        embed.set_author(name=channel.long_name, url=channel.url)
        return embed

    @staticmethod
    def build_embed_ustats(user: dict):
        user_name = user.get('name')
        user_id = user.get('user_id')
        user_url = f'https://rainwave.cc/#!/listener/{user_id}'
        user_colour = int(user.get('colour'), 16)
        embed = discord.Embed(title=user_name, url=user_url, description='Rainwave user stats', colour=user_colour)
        user_avatar = user.get('avatar')
        embed.set_thumbnail(url=f'https://rainwave.cc{user_avatar}')
        embed.add_field(name='Game', value=f'{user.get("rating_completion").get("1")}% rated', inline=True)
        embed.add_field(name='Chiptune', value=f'{user.get("rating_completion").get("4")}% rated', inline=True)
        embed.add_field(name='OC ReMix', value=f'{user.get("rating_completion").get("2")}% rated', inline=True)
        embed.add_field(name='Covers', value=f'{user.get("rating_completion").get("3")}% rated', inline=True)
        return embed

    @commands.command(aliases=['nx'] + [f'nx{ch}' for ch in RainwaveChannel.__members__.keys()])
    async def next(self, ctx: commands.Context, channel: str = None):
        """See what will play next on the radio.

        Use "!next [<channel>]" to show what is up next on the radio.
        Short version is "!nx[<channel>]".
        Leave off <channel> to auto-detect the channel you are tuned to."""

        cmd = ctx.invoked_with
        chan = None
        idx = 0

        if cmd in ['nxgame', 'nxrw']:
            chan = RainwaveChannel.game
        elif cmd in ['nxoc', 'nxocr', 'nxocremix']:
            chan = RainwaveChannel.ocr
        elif cmd in ['nxcover', 'nxcovers', 'nxmw', 'nxvw']:
            chan = RainwaveChannel.covers
        elif cmd in ['nxbw', 'nxch', 'nxchip', 'nxchiptune']:
            chan = RainwaveChannel.chip
        elif cmd in ['nxall', 'nxomni', 'nxow']:
            chan = RainwaveChannel.all
        elif cmd in ['next', 'nx']:
            if channel:
                if channel.lower() in RainwaveChannel.__members__.keys():
                    chan = RainwaveChannel[channel.lower()]
            if chan is None:
                chan = await self.get_current_channel_for_user(ctx.author)
            if chan is None:
                await ctx.author.send(self.not_tuned_in)
                return

        m = f'Next up on the {chan.long_name}'
        d = await self.rw_info(chan.channel_id)
        event = d.get('sched_next')[idx]
        sched_id = int(event.get('id'))
        sched_type = event.get('type')
        sched_name = event.get('name')
        if sched_type == 'OneUp':
            m += f' ({sched_name} Power Hour):'
            song = event.get('songs')[0]
            m += f' {self.song_string(song)}'
        elif sched_type == 'Election':
            if sched_name:
                m += f' ({sched_name})'
            m += f':'
            for i, s in enumerate(event.get('songs'), start=1):
                song_string = self.song_string(s, simple=True)
                m += f' **[{i}]** {song_string}'
                req = s.get('elec_request_username')
                if req:
                    m += f' (requested by {req})'

        if ctx.guild:
            config_id = f'rainwave:nx:{chan.channel_id}:{idx}'
            if sched_id == (self.bot.db.config_get(config_id) or 0):
                c = f'You can only use **{cmd}** in {ctx.channel.mention} once per song.'
                await ctx.author.send(c)
                await ctx.author.send(m)
            else:
                self.bot.db.config_set(config_id, sched_id)
                await ctx.send(m)
        else:
            await ctx.send(m)

    @commands.command(aliases=['np'] + [f'np{ch}' for ch in RainwaveChannel.__members__.keys()])
    async def nowplaying(self, ctx: commands.Context, channel: str = None):
        """See what is now playing on the radio.

        Use "!nowplaying [<channel>]" to show what is now playing on the radio.
        Short version is "!np[<channel>]".
        Leave off <channel> to auto-detect the channel you are tuned to."""

        async with ctx.typing():
            cmd = ctx.invoked_with
            chan = None

            if cmd in ['npgame', 'nprw']:
                chan = RainwaveChannel.game
            elif cmd in ['npoc', 'npocr', 'npocremix']:
                chan = RainwaveChannel.ocr
            elif cmd in ['npcover', 'npcovers', 'npmw', 'npvw']:
                chan = RainwaveChannel.cover
            elif cmd in ['npbw', 'npch', 'npchip', 'npchiptune']:
                chan = RainwaveChannel.chip
            elif cmd in ['npall', 'npomni', 'npow']:
                chan = RainwaveChannel.all
            elif cmd in ['nowplaying', 'np']:
                if channel and channel.lower() in RainwaveChannel.__members__.keys():
                    chan = RainwaveChannel[channel.lower()]
                if chan is None:
                    chan = await self.get_current_channel_for_user(ctx.author)
                if chan is None:
                    await ctx.author.send(self.not_tuned_in)
                    return

            m = f'Now playing on the {chan.long_name}'
            d = await self.rw_info(chan.channel_id)
            event = d.get('sched_current')
            sched_id = int(event.get('id'))
            sched_type = event.get('type')
            sched_name = event.get('name')
            if sched_type == 'Election' and sched_name:
                m += f' ({sched_name})'
            elif sched_type == 'OneUp':
                m += f' ({sched_name} Power Hour)'
            song = event.get('songs')[0]
            embed = self.build_embed(song)
            m += f': {self.song_string(song)}'

            if ctx.guild:
                last = self.bot.db.config_get(f'rainwave:np:{chan.channel_id}') or 0
                if sched_id == last:
                    c = f'You can only use **{cmd}** in {ctx.channel.mention} once per song.'
                    await ctx.author.send(c)
                    await ctx.author.send(m, embed=embed)
                else:
                    self.bot.db.config_set(f'rainwave:np:{chan.channel_id}', sched_id)
                    await ctx.send(m, embed=embed)
            else:
                await ctx.send(m, embed=embed)

    @commands.command(aliases=['pp'] + [f'pp{ch}' for ch in RainwaveChannel.__members__.keys()])
    async def prevplayed(self, ctx: commands.Context, *, args: str = None):
        """Show what was previously playing on the radio.

        Use "!prevplayed [<channel>] [<index>]" to show what was previously playing on the radio.
        Short version is "!pp[<channel>] [<index>]".
        Leave off <channel> to auto-detect the channel you are tuned to.
        <index> should be a number from 0 to 4 (default 0). The higher the number, the further back in time you go."""

        async with ctx.typing():
            cmd = ctx.invoked_with
            if args is None:
                args = ''
            tokens = args.split()

            chan = None
            idx = 0

            if cmd in ['ppgame', 'pprw']:
                chan = RainwaveChannel.game
            elif cmd in ['ppoc', 'ppocr', 'ppocremix']:
                chan = RainwaveChannel.ocr
            elif cmd in ['ppcover', 'ppcovers', 'ppmw', 'ppvw']:
                chan = RainwaveChannel.cover
            elif cmd in ['ppbw', 'ppch', 'ppchip', 'ppchiptune']:
                chan = RainwaveChannel.chip
            elif cmd in ['ppall', 'ppomni', 'ppow']:
                chan = RainwaveChannel.all

            if chan and chan in RainwaveChannel and len(tokens) > 0 and tokens[0].isdigit():
                if int(tokens[0]) in range(5):
                    idx = int(tokens[0])

            if cmd in ['prevplayed', 'pp']:
                if len(tokens) > 0:
                    if tokens[0].isdigit() and int(tokens[0]) in range(5):
                        idx = int(tokens[0])
                    else:
                        if tokens[0].lower() in RainwaveChannel.__members__.keys():
                            chan = RainwaveChannel[tokens[0].lower()]
                        if len(tokens) > 1:
                            if tokens[1].isdigit() and int(tokens[1]) in range(5):
                                idx = int(tokens[1])
                if chan is None:
                    chan = await self.get_current_channel_for_user(ctx.author)
                if chan is None:
                    await ctx.author.send(self.not_tuned_in)
                    return

            m = f'Previously on the {chan.long_name}'
            d = await self.rw_info(chan.channel_id)
            event = d.get('sched_history')[idx]
            sched_id = int(event.get('id'))
            sched_type = event.get('type')
            sched_name = event.get('name')
            if sched_type == 'Election' and sched_name:
                m += f' ({sched_name})'
            elif sched_type == 'OneUp':
                m += f' ({sched_name} Power Hour)'
            song = event.get('songs')[0]
            embed = self.build_embed(song)
            m += f': {self.song_string(song)}'

            if ctx.guild:
                config_key = f'rainwave:pp:{chan.channel_id}:{idx}'
                last = self.bot.db.config_get(config_key) or 0
                if sched_id == last:
                    await ctx.author.send(f'You can only use {cmd} in {ctx.channel.mention} once per song.')
                    await ctx.author.send(m, embed=embed)
                else:
                    self.bot.db.config_set(config_key, sched_id)
                    await ctx.send(m, embed=embed)
            else:
                await ctx.send(m, embed=embed)

    @commands.command(aliases=['rq'])
    async def request(self, ctx: commands.Context, *, args: str = None):
        """Manage your Rainwave request queue.

        Use "!rq <song_id>" to add a song to your request queue.
        Use "!rq unrated" to fill your request queue with unrated songs.
        Use "!rq fav" to add favourite songs to your request queue.
        Use "!rq pause" to pause your request queue.
        Use "!rq resume" to resume your request queue.
        Use "!rq clear" to remove all songs from your request queue."""

        if args is None:
            args = ''
        tokens = args.split()

        if len(tokens) < 1:
            await ctx.author.send('Command not complete.')
            return

        auth = await self.get_api_auth_for_user(ctx.author)
        if auth.get('user_id') is None:
            await ctx.author.send(self.nick_not_recognized)
            return
        if auth.get('key') is None:
            await ctx.author.send(self.missing_key)
            return
        if auth.get('chan') is None:
            await ctx.author.send('You must be tuned in to request.')
            return

        if tokens[0].isdigit():
            song_id = int(tokens[0])
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = await self.rw_song(user_id, key, chan_id, song_id)
            song = d.get('song')
            song_str = self.song_string(song, simple=True)
            await ctx.author.send(f'Attempting request: {song_str}')
            d = await self.rw_request(user_id, key, chan_id, song_id)
            await ctx.author.send(d.get('request_result').get('text'))

        elif tokens[0] == 'unrated':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = await self.rw_request_unrated_songs(user_id, key, chan_id)
            await ctx.author.send(d.get('request_unrated_songs_result').get('text'))

        elif tokens[0] == 'fav':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = await self.rw_request_favorited_songs(user_id, key, chan_id)
            await ctx.author.send(d.get('request_favorited_songs_result').get('text'))

        elif tokens[0] == 'clear':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            await self.rw_clear_requests(user_id, key, chan_id)
            await ctx.author.send('Request queue cleared.')

        elif tokens[0] == 'pause':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = await self.rw_pause_request_queue(user_id, key, chan_id)
            await ctx.author.send(d.get('pause_request_queue_result').get('text'))

        elif tokens[0] == 'resume':
            user_id = auth.get('user_id')
            key = auth.get('key')
            chan_id = auth.get('chan').channel_id
            d = await self.rw_unpause_request_queue(user_id, key, chan_id)
            await ctx.author.send(d.get('unpause_request_queue_result').get('text'))

    @commands.command()
    async def ustats(self, ctx: commands.Context, *, username: str = None):
        """See some statistics about a Rainwave user.

        Use "!ustats [<username>]" to see some statistics about a Rainwave user.
        Leave off <username> to see your own stats."""

        async with ctx.typing():
            log.info(f'username: {username!r}')

            if username is None:
                listener_id = await self.get_id_for_user(ctx.author)
                if listener_id is None:
                    await ctx.author.send(f'Use **!id add <id>** to connect your Rainwave and Discord accounts.')
                    return
            elif username.startswith('<@') and username.endswith('>') and username[2:-1].isdigit():
                member = discord.utils.get(ctx.guild.members, id=int(username[2:-1]))
                username = member.display_name
                listener_id = await self.get_id_for_user(member)
            else:
                listener_id = await self.get_id_for_name(username)

            if listener_id is None:
                await ctx.author.send(f'{username} is not a valid Rainwave user.')
                return

            user_id = self.bot.db.config_get('rainwave:user_id')
            key = self.bot.db.config_get('rainwave:key')
            d = await self.rw_listener(user_id, key, listener_id)
            embed = self.build_embed_ustats(d.get('listener'))

            user_name = d.get('listener').get('name')
            current_channel = await self.get_current_channel_for_name(user_name)
            if current_channel:
                embed.set_footer(text=f'Currently listening to the {current_channel.long_name}')

            if not ctx.guild:
                await ctx.send(embed=embed)
                return

            now = int(time.time())
            last = int(self.bot.db.config_get('rainwave:ustats:last') or 0)
            wait = int(self.bot.db.config_get('rainwave:ustats:wait') or 0)
            if last < now - wait:
                await ctx.send(embed=embed)
                self.bot.db.config_set('rainwave:ustats:last', now)
            else:
                await ctx.author.send(embed=embed)
                remaining = last + wait - now
                cmd = ctx.invoked_with
                m = (f'I am cooling down. You cannot use **{cmd}** in {ctx.channel.mention} for another {remaining} '
                     f'seconds.')
                await ctx.author.send(m)

    @commands.command(aliases=['vt'])
    async def vote(self, ctx: commands.Context, candidate: int):
        """Vote in the current election.

        Use "!vote <candidate>" to vote in the current election.
        Find the <candidate> (usually a number from 1 to 3) with "!next"."""

        auth = await self.get_api_auth_for_user(ctx.author)
        if auth.get('user_id') is None:
            await ctx.author.send(self.nick_not_recognized)
            return
        if auth.get('key') is None:
            await ctx.author.send(self.missing_key)
            return
        if auth.get('chan') is None:
            await ctx.author.send('You must be tuned in to vote.')
            return

        chan = auth.get('chan')
        d = await self.rw_info(chan.channel_id)
        event = d.get('sched_next')[0]
        sched_type = event.get('type')

        if sched_type == 'OneUp':
            await ctx.author.send('You cannot vote during a Power Hour.')
            return

        if candidate < 1 or candidate > len(event.get('songs')):
            await ctx.author.send(f'{candidate} is not a valid voting option')
            return

        song = event.get('songs')[candidate - 1]
        elec_entry_id = song.get('entry_id')
        user_id = auth.get('user_id')
        key = auth.get('key')
        d = await self.rw_vote(user_id, key, chan.channel_id, elec_entry_id)
        if d.get('vote_result').get('success'):
            song_string = self.song_string(song, simple=True)
            await ctx.author.send(f'You successfully voted for {song_string}')
        else:
            await ctx.author.send('Your attempt to vote was not successful.')

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        donor_role_id = self.bot.db.config_get('discord:roles:donor')
        patron_role_id = self.bot.db.config_get('discord:roles:patron')
        if donor_role_id is not None and patron_role_id is not None:
            donor_role = before.guild.get_role(int(donor_role_id))
            patron_role = before.guild.get_role(int(patron_role_id))
            is_donor = donor_role in after.roles
            is_patron = patron_role in after.roles
            if is_donor or is_patron:
                await self.rw_enable_perks([after])
                if not is_donor:
                    await after.add_roles(donor_role)
        if before.display_name != after.display_name:
            log.info(f'{before.display_name!r} ({before.id}) changed display_name to {after.display_name!r}')
            await self.rw_update_nickname(after.id, after.display_name)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before.display_avatar != after.display_avatar:
            await self.rw_update_avatar(after.id, after.display_avatar)

    async def _sync_donors(self, guild: discord.Guild):
        donor_role_id = self.bot.db.config_get('discord:roles:donor')
        patron_role_id = self.bot.db.config_get('discord:roles:patron')
        if donor_role_id is not None and patron_role_id is not None:
            donor_role = guild.get_role(int(donor_role_id))
            await self.rw_enable_perks(donor_role.members)
            patron_role = guild.get_role(int(patron_role_id))
            for patron_member in patron_role.members:
                if donor_role not in patron_member.roles:
                    await patron_member.add_roles(donor_role)

    @commands.command()
    @commands.is_owner()
    async def sync_donors(self, ctx: commands.Context):
        for guild in self.bot.guilds:
            await self._sync_donors(guild)

    @commands.Cog.listener()
    async def on_ready(self):
        if self.bot.db.config_get('rainwave:sync_donor_role_on_ready') == '1':
            for guild in self.bot.guilds:
                log.info(f'Syncing donors for guild {guild.id}')
                await self._sync_donors(guild)

    def cog_unload(self):
        self.sync_events.cancel()


async def setup(bot: Wormgas):
    await bot.add_cog(RainwaveCog(bot))
