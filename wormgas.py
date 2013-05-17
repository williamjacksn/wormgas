#!/usr/bin/env python
'''
wormgas -- IRC bot for Rainwave (http://rainwave.cc)
https://github.com/williamjacksn/wormgas
'''

import json
import logging
import logging.handlers
import math
import os
import random
import re
import requests
import subprocess
import sys
import time
from urlparse import urlparse

import dbaccess
import rainwave
import util
from irc.bot import SingleServerIRCBot
from cobe.brain import Brain

_abspath = os.path.abspath(__file__)
_commands = set()

PRIVMSG = u'__privmsg__'


class Output(object):
	'''Dead-simple abstraction for splitting output between public and private.

	When created, specify the default output, either public or private. This
	way command handlers don't have to care about the output mode unless they
	need to.
	'''
	def __init__(self, default):
		'''Create an Output object.

		Args:
			default: string, either u'public' or u'private'.
		'''
		self.rs = []
		self.privrs = []
		if default == u'public':
			self._default = self.rs
		elif default == u'private':
			self._default = self.privrs
		else:
			raise ValueError(u'default should be u\'public\' or u\'private\'')

	@property
	def default(self):
		'''The default output list.'''
		return self._default


def command_handler(command):
	'''Decorate a method to register as a command handler for provided regex.'''
	def decorator(func):
		# Compile the command into a regex.
		regex = re.compile(command, re.I)

		def wrapped(self, nick, msg, channel, output):
			'''Command with stored regex that will execute if it matches msg.'''
			# If the regex does not match the message, return False.
			result = regex.search(msg)
			if not result:
				return False

			# The msg matches pattern for this command, so run it.
			func(self, nick, channel, output, **result.groupdict())
			return True
		# Add the wrapped function to a set, so we can iterate over them later.
		_commands.add(wrapped)

		# Return the original, undecorated method. It can still be called
		# directly without worrying about regexes. This also allows registering
		# one method as a handler for multiple input regexes.
		return func
	return decorator


class wormgas(SingleServerIRCBot):

	channel_codes = (
		None,
		u'game',
		u'ocr',
		u'cover',
		u'chip',
		u'all'
	)

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

	def __init__(self, config_db=u'config.sqlite', log_file=u'wormgas.log'):
		self.path, self.file = os.path.split(_abspath)
		self.brain = Brain(self.path + u'/brain.sqlite')
		self.config = dbaccess.Config(u'{}/{}'.format(self.path, config_db))
		self.ph = util.CollectionOfNamedLists(u'{}/ph.json'.format(self.path))
		self.rq = util.CollectionOfNamedLists(u'{}/rq.json'.format(self.path))
		self.rw = rainwave.RainwaveClient()
		self.tf = util.TitleFetcher()

		# Set up logging.
		self.log = logging.getLogger(u'wormgas')
		self.log_handler = None
		if log_file:
			self.log.setLevel(logging.DEBUG)
			logpath = u'{}/{}'.format(self.path, log_file)
			self.log_handler = logging.handlers.RotatingFileHandler(
				logpath, maxBytes=20000000, backupCount=1)
			self.log_handler.setFormatter(logging.Formatter(
				u'%(asctime)s - %(levelname)s - %(message)s'))
			logging.getLogger().addHandler(self.log_handler)

		# Set up Rainwave DB access if available.
		try:
			self.rwdb = dbaccess.RainwaveDatabase(self.config)
			self.rwdb.connect()
		except dbaccess.RainwaveDatabaseUnavailableError:
			self.rwdb = None
			self.rwdberr = u'The Rainwave database is unavailable.'

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
			self.reignore = re.compile(ignore)

		server = self.config.get(u'irc:server')
		nick = self.config.get(u'irc:nick')
		name = self.config.get(u'irc:name')
		SingleServerIRCBot.__init__(self, [(server, 6667)], nick, name)
		self.connection.buffer_class.errors = u'replace'

	def stop(self):
		'''Save all data and shut down the bot.'''
		del self.config
		del self.brain
		if self.log_handler:
			logging.getLogger().removeHandler(self.log_handler)

	def _dispatcher(self, c, e):
		et = e.type
		if et not in self._events_not_logged():
			s = e.source
			t = e.target
			self.log.debug(u'{}, {}, {} -- {}'.format(et, s, t, e.arguments))
		SingleServerIRCBot._dispatcher(self, c, e)

	@command_handler(u'!8ball')
	def handle_8ball(self, nick, channel, output):
		'''Ask a question of the magic 8ball.'''

		self.log.info(u'{} used !8ball'.format(nick))

		result = random.choice(self._answers_8ball())
		# Private messages always get the result.
		if channel == PRIVMSG:
			output.default.append(result)
			return

		# Otherwise, check for the cooldown and respond accordingly.
		ltb = int(self.config.get(u'lasttime:8ball', 0))
		wb = int(self.config.get(u'wait:8ball', 0))
		if ltb < time.time() - wb:
			output.default.append(result)
			if u'again' not in result:
				self.config.set(u'lasttime:8ball', time.time())
		else:
			output.privrs.append(result)
			wait = ltb + wb - int(time.time())
			r = u'I am cooling down. You cannot use !8ball in '
			r += u'{} for another {} seconds.'.format(channel, wait)
			output.privrs.append(r)

	@command_handler(u'^!c(ool)?d(own)? add(\s(?P<unit>\w+))?'
		u'(\s(?P<unit_id>\d+))?(\s(?P<cdg_name>.+))?')
	def handle_cooldown_add(self, nick, channel, output, unit=None,
		unit_id=None, cdg_name=None):
		'''Add a song or album to a cooldown group.'''

		self.log.info(u'{} used !cooldown add'.format(nick))
		self.log.info(u'unit: {}, unit_id: {}, cdg_name: {}'.format(unit, unit_id,
			cdg_name))

		# This command requires administrative privileges
		if not self._is_admin(nick):
			m = u'{} does not have privs to use !cooldown add'
			self.log.warning(m.format(nick))
			return

		# This command requires the Rainwave database
		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		# cdg_name must be specified
		if cdg_name is None:
			self.handle_help(nick, channel, output, topic=u'cooldown')
			return

		# unit_id should be numeric
		if unit_id is None:
			self.handle_help(nick, channel, output, topic=u'cooldown')
			return

		if unit_id.isdigit():
			unit_id = int(unit_id)
		else:
			self.handle_help(nick, channel, output, topic=u'cooldown')
			return

		# unit should be 'song' or 'album'

		if unit == u'song':
			rcode, rval = self.rwdb.add_song_to_cdg(unit_id, cdg_name)
			if rcode == 0:
				rchan = self.rw.channel_id_to_name(rval[0])
				rval = (rchan,) + rval[1:]
				r = u'Added {} / {} / {} to cooldown group {}'.format(*rval)
				output.privrs.append(r)
			else:
				output.privrs.append(rval)
		elif unit == u'album':
			rcode, rval = self.rwdb.add_album_to_cdg(unit_id, cdg_name)
			if rcode == 0:
				rchan = self.rw.channel_id_to_name(rval[0])
				rval = (rchan,) + rval[1:]
				r = u'Added {} / {} to cooldown group {}'.format(*rval)
				output.privrs.append(r)
			else:
				output.privrs.append(rval)
		else:
			self.handle_help(nick, channel, output, topic=u'cooldown')

	@command_handler(u'^!c(ool)?d(own)? drop(\s(?P<unit>\w+))?'
		u'(\s(?P<unit_id>\d+))?(\s(?P<cdg_name>.+))?')
	def handle_cooldown_drop(self, nick, channel, output, unit=None,
		unit_id=None, cdg_name=None):
		'''Remove a song or album from a cooldown group'''

		self.log.info(u'{} used !cooldown drop'.format(nick))
		self.log.info(u'unit: {}, unit_id: {}, cdg_name: {}'.format(unit, unit_id,
			cdg_name))

		# This command requires administrative privileges

		if not self._is_admin(nick):
			m = u'{} does not have privs to use !cooldown add'
			self.log.warning(m.format(nick))
			return

		# This command requires the Rainwave database

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		# unit_id should be numeric

		if unit_id is None:
			self.handle_help(nick, channel, output, topic=u'cooldown')
			return

		if unit_id.isdigit():
			unit_id = int(unit_id)
		else:
			self.handle_help(nick, channel, output, topic=u'cooldown')
			return

		# unit should be 'song' or 'album'

		if unit == u'song':
			if cdg_name is None:
				rcode, rval = self.rwcd.drop_song_from_all_cdgs(unit_id)
				if rcode == 0:
					rchan = self.rw.channel_id_to_name(rval[0])
					rval = (rchan,) + rval[1:]
					r = u'Dropped {} / {} / {} from all cooldown groups'.format(*rval)
					output.privrs.append(r)
				else:
					output.privrs.append(rval)
			else:
				rcode, rval = self.rwdb.drop_song_from_cdg_by_name(unit_id, cdg_name)
				if rcode == 0:
					rchan = self.rw.channel_id_to_name(rval[0])
					rval = (rchan,) + rval[1:]
					r = u'Dropped {} / {} / {} from cooldown group {}'.format(*rval)
					output.privrs.append(r)
				else:
					output.privrs.append(rval)
		elif unit == u'album':
			if cdg_name is None:
				rcode, rval = self.rwdb.drop_album_from_all_cdgs(unit_id)
				if rcode == 0:
					rchan = self.rw.channel_id_to_name(rval[0])
					rval = (rchan,) + rval[1:]
					r = u'Dropped {} / {} from all cooldown groups'.format(*rval)
					output.privrs.append(r)
				else:
					output.privrs.append(rval)
			else:
				rcode, rval = self.rwdb.drop_album_from_cdg_by_name(unit_id, cdg_name)
				if rcode == 0:
					rchan = self.rw.channel_id_to_name(rval[0])
					rval = (rchan,) + rval[1:]
					r = u'Dropped {} / {} from cooldown group {}'.format(*rval)
					output.privrs.append(r)
				else:
					output.privrs.append(rval)
		else:
			self.handle_help(nick, channel, output, topic=u'cooldown')

	@command_handler(u'!election(\s(?P<rchan>\w+))?(\s(?P<index>\d))?')
	@command_handler(u'!el(?P<rchan>\w+)?(\s(?P<index>\d))?')
	def handle_election(self, nick, channel, output, rchan=None, index=None):
		'''Show the candidates in an election'''

		self.log.info(u'{} used !election'.format(nick))

		# Make sure the index is valid.
		try:
			index = int(index)
		except TypeError:
			index = 0
		if index not in [0, 1]:
			# Not a valid index, return the help text.
			self.handle_help(nick, channel, output, topic=u'election')
			return

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append(u'I cannot determine the channel.')
				self.handle_help(nick, channel, output, topic=u'election')
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic=u'election')
			return

		sched_config = u'el:{}:{}'.format(cid, index)
		sched_id, text = self._fetch_election(index, cid)

		if sched_id == 0:
			# Something strange happened while fetching the election
			output.default.append(text)
			return

		# Prepend the message description to the output string.
		time = [u'Current', u'Future'][index]
		rchn = self.rw.channel_id_to_name(cid)  # radio channel name
		result = u'{} election on the {}: {}'.format(time, rchn, text)

		if channel == PRIVMSG:
			output.privrs.append(result)
		elif sched_id == self.config.get(sched_config):
			# !election has already been called for this election
			output.privrs.append(result)
			r = u'I am cooling down. You can only use !election in '
			r += u'{} once per election.'.format(channel)
			output.privrs.append(r)
		else:
			output.default.append(result)
			self.config.set(sched_config, sched_id)

	def _fetch_election(self, index, cid):
		'''Return (sched_id, election string) for given index and cid.

		A sched_id is a unique ID given to every scheduled event, including
		elections. The results of this call can therefore be cached locally
		using the sched_id as the cache key.
		'''

		text = u''

		data = self.rw.get_timeline(cid)
		try:
			elec = data[u'sched_next'][index]
		except IndexError:
			# There is no future election?
			return 0, u'There is no election at the specified index.'

		for i, song in enumerate(elec[u'song_data'], start=1):
			album = song[u'album_name']
			title = song[u'song_title']
			artt = u', '.join(art[u'artist_name'] for art in song[u'artists'])
			text += u' \x02[{}]\x02 {} / {} by {}'.format(i, album, title, artt)
			etype = song[u'elec_isrequest']
			if etype in (3, 4):
				requestor = song[u'song_requestor']
				text += u' (requested by {})'.format(requestor)
			elif etype in (0, 1):
				text += u' (conflict)'
		return elec[u'sched_id'], text

	@command_handler(u'^!fav(?P<argstring>.*)')
	def handle_fav(self, nick, channel, output, argstring=u''):
		'''Show a list of favourite songs for a user'''

		self.log.info(u'{} use !fav'.format(nick))

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return

		limit = 1
		radio_channel_id = self._get_current_channel_for_nick(nick)

		args = argstring.split()

		if len(args) > 0:
			if args[0] in self.channel_ids:
				radio_channel_id = self.channel_ids[args[0]]
				if len(args) > 1 and args[1].isdigit():
						limit = int(args[1])
			else:
				radio_channel_id = self._get_current_channel_for_nick(nick)
				if args[0].isdigit():
					limit = int(args[0])

		if radio_channel_id is None:
			m = u'You are not tuned in and you did not specify a channel code.'
			output.privrs.append(m)
			self.handle_help(nick, channel, output, topic=u'fav')
			return
		radio_channel_id = int(radio_channel_id)

		fav = self.rwdb.get_fav_songs(api_auth[u'user_id'], radio_channel_id)

		if len(fav) == 0:
			output.privrs.append(u'No favourite songs.')
			return

		i = 0
		while i < limit and i < int(self.config.get(u'maxlength:unrated', 12)):
			if len(fav) > 0:
				song_id = fav.pop(0)
			else:
				output.privrs.append(u'No more albums with favourite songs.')
				return
			output.privrs.append(self._get_song_info_string(song_id))
			i += 1

	@command_handler(u'!flip')
	def handle_flip(self, nick, channel, output):
		'''Simulate a coin flip'''

		self.log.info(u'{} used !flip'.format(nick))

		answers = (u'Heads!', u'Tails!')
		result = random.choice(answers)
		if channel == PRIVMSG:
			output.default.append(result)
			return

		ltf = int(self.config.get(u'lasttime:flip', 0))
		wf = int(self.config.get(u'wait:flip', 0))
		if ltf < time.time() - wf:
			output.default.append(result)
			self.config.set(u'lasttime:flip', time.time())
		else:
			output.privrs.append(result)
			wait = ltf + wf - int(time.time())
			r = u'I am cooling down. You cannot use !flip in {} '.format(channel)
			r += u'for another {} seconds.'.format(wait)
			output.privrs.append(r)

	@command_handler(u'!forum')
	def handle_forum(self, nick, channel, output, force=True):
		'''Check for new forum posts, excluding forums where the anonymous user
		has no access'''

		self.log.info(u'Looking for new forum posts, force is {}'.format(force))

		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !forum'.format(nick))
			return

		self.config.set(u'lasttime:forumcheck', time.time())

		if force:
			self.config.unset(u'maxid:forum')

		maxid = self.config.get(u'maxid:forum', 0)
		self.log.info(u'Looking for forum posts newer than {}'.format(maxid))

		if self.rwdb:
			newmaxid = self.rwdb.get_max_forum_post_id()
		else:
			output.privrs.append(self.rwdberr)
			return

		if newmaxid > int(self.config.get(u'maxid:forum', 0)):
			r, url = self.rwdb.get_forum_post_info()
			surl = self._shorten(url)
			output.rs.append(u'New on the forums! {} <{}>'.format(r, surl))
			self.config.set(u'maxid:forum', newmaxid)

	@command_handler(u'^!help(\s(?P<topic>\w+))?')
	def handle_help(self, nick, channel, output, topic=None):
		'''Look up help about a topic'''

		self.log.info(u'{} used !help'.format(nick))

		is_admin = self._is_admin(nick)
		rs = []

		channelcodes = (u'Channel codes are \x02' +
			u'\x02, \x02'.join(self.channel_ids.keys()) + u'\x02.')
		notpermitted = u'You are not permitted to use this command.'
		wiki = (u'More help is available at '
			u'https://github.com/williamjacksn/wormgas/wiki')

		if topic in [u'all', None]:
			rs.append(u'Use \x02!help [<topic>]\x02 with one of these topics: '
				u'8ball, election, fav, flip, history, id, key, lookup, lstats, '
				u'nowplaying, prevplayed, rate, roll, rps, rq, stats, '
				u'unrated, ustats, vote.')
			if is_admin:
				rs.append(u'Administration topics: cooldown, forum, newmusic, otp, ph, '
					u'refresh, restart, set, stop, unset.')
			rs.append(wiki)
		elif topic == u'8ball':
			rs.append(u'Use \x02!8ball\x02 to ask a question of the magic 8ball.')
		elif topic in [u'cooldown', u'cd']:
			if is_admin:
				rs.append(u'Use \x02!cooldown add song|album <song_id|album_id> '
					u'<cdg_name>\x02 to add a song or album to a cooldown group.')
				rs.append(u'Use \x02!cooldown drop song|album '
					u'<song_id|album_id> [<cdg_name>]\x02 to remove a song or '
					u'album from a cooldown group, leave off <cdg_name> to '
					u'remove a song or album from all cooldown groups.')
				rs.append(u'Short version is \x02!cd ...\x02')
			else:
				rs.append(notpermitted)
		elif topic in [u'election', u'el']:
			rs.append(u'Use \x02!election <channel> [<index>]\x02 to see the '
				u'candidates in an election.')
			rs.append(u'Short version is \x02!el<channel> [<index>]\x02.')
			rs.append(u'Index should be 0 (current) or 1 (future), default is 0.')
			rs.append(channelcodes)
		elif topic == u'fav':
			rs.append(u'Use \x02!fav [<channel>] [<limit>] to see songs you have '
				u'marked favourite, <limit> can go up to 12, leave it off to see just '
				u'one song.')
			rs.append(u'Leave off <channel> to use the channel you are currently '
				u'tuned to.')
			rs.append(channelcodes)
		elif topic == u'flip':
			rs.append(u'Use \x02!flip\x02 to flip a coin.')
		elif topic == u'forum':
			if is_admin:
				rs.append(u'Use \x02!forum\x02 to announce the most recent forum post '
					u'in the channel.')
			else:
				rs.append(notpermitted)
		elif topic in [u'history', u'hs']:
			rs.append(u'Use \x02!history <channel>\x02 to see the last several '
				u'songs that played on a channel.')
			rs.append(u'Short version is \x02!hs<channel>\x02.')
			rs.append(channelcodes)
		elif topic == u'id':
			rs.append(u'Look up your Rainwave user id at http://rainwave.cc/auth/ '
				u'and use \x02!id add <id>\x02 to tell me about it.')
			rs.append(u'Use \x02!id drop\x02 to delete your user id and \x02!id '
				u'show\x02 to see it.')
		elif topic == u'key':
			rs.append(u'Get an API key from http://rainwave.cc/auth/ and use '
				u'\x02!key add <key>\x02 to tell me about it.')
			rs.append(u'Use \x02!key drop\x02 to delete your key and \x02!key '
				u'show\x02 to see it.')
		elif topic in [u'lookup', u'lu']:
			rs.append(u'Use \x02!lookup <channel> song|album <text>\x02 '
				u'to search for songs or albums with <text> in the title.')
			rs.append(u'Short version is \x02!lu<channel> song|album <text>\x02.')
			rs.append(channelcodes)
		elif topic == u'lstats':
			rs.append(u'Use \x02!lstats [<channel>]\x02 to see information about '
				u'current listeners, all channels are aggregated if you leave off '
				u'<channel>.')
			rs.append(u'Use \x02!lstats chart [<num>]\x02 to see a chart of average '
				u'hourly listener activity over the last <num> days, leave off <num> '
				u'to use the default of 30.')
			rs.append(channelcodes)
		elif topic == u'newmusic':
			if is_admin:
				rs.append(u'Use \x02!newmusic <channel>\x02 to announce the three most '
					u'recently added songs on the channel.')
				rs.append(channelcodes)
			else:
				rs.append(notpermitted)
		elif topic in [u'nowplaying', u'np']:
			rs.append(u'Use \x02!nowplaying <channel>\x02 to show what is now '
				u'playing on the radio.')
			rs.append(u'Short version is \x02!np<channel>\x02.')
			rs.append(channelcodes)
		elif topic == u'otp':
			if is_admin:
				rs.append(u'Use \x02!otp\x02 to see all One-Time Plays currently '
					u'scheduled on all channels.')
			else:
				rs.append(notpermitted)
		elif topic == u'ph':
			if is_admin:
				rs.append(u'Use \x02!ph <command>\x02 to manage your Power Hour '
					u'planning list.')
				rs.append(u'Refer to https://github.com/williamjacksn/wormgas/wiki/ph '
					u'for details.')
			else:
				rs.append(notpermitted)
		elif topic in [u'prevplayed', u'pp']:
			rs.append(u'Use \x02!prevplayed <channel> [<index>]\x02 to show what was '
				u'previously playing on the radio.')
			rs.append(u'Short version is \x02!pp<channel> [<index>]\x02.')
			rs.append(u'Index should be one of (0, 1, 2), 0 is default, higher '
				u'numbers are further in the past.')
			rs.append(channelcodes)
		elif topic in [u'rate', u'rt']:
			rs.append(u'Use \x02!rate <channel> <rating>\x02 to rate the currently '
				u'playing song.')
			rs.append(u'Short version is \x02!rt<channel> <rating>\x02.')
			rs.append(channelcodes)
		elif topic == u'refresh':
			if is_admin:
				rs.append(u'Use \x02!refresh\x02 to show pending or running playlist '
					u'refresh jobs.')
				rs.append(u'Use \x02!refresh <channel>\x02 to request a playlist '
					u'refresh for a particular channel.')
				rs.append(channelcodes)
			else:
				rs.append(notpermitted)
		elif topic == u'restart':
			if is_admin:
				rs.append(u'Use \x02!restart\x02 to restart the bot.')
			else:
				rs.append(notpermitted)
		elif topic == u'roll':
			rs.append(u'Use \x02!roll [#d^]\x02 to roll a ^-sided die # times.')
		elif topic == u'rps':
			rs.append(u'Use \x02!rock\x02, \x02!paper\x02, or \x02!scissors\x02 to '
				u'play a game.')
			rs.append(u'Use \x02!rps record [<nick>]\x02 to see the record for '
				u'<nick>, leave off <nick> to see your own record, use nick '
				u'\'!global\' to see the global record.')
			rs.append(u'Use \x02!rps stats [<nick>]\x02 to see some statistics for '
				'<nick>, leave off <nick> to see your own statistics.')
			rs.append(u'Use \x02!rps reset\x02 to reset your record and delete your '
				'game history, there is no confirmation and this cannot be undone.')
			rs.append(u'Use \x02!rps who\x02 to see a list of known players')
			if is_admin:
				rs.append(u'Administrators can use \x02!rps rename <oldnick> '
					u'<newnick>\x02 to reassign stats and game history from one nick to '
					u'another.')
		elif topic == u'rq':
			rs.append(u'Use \x02!rq <song_id>\x02 to add a song to your request '
				'queue, find the <song_id> using \x02!lookup\x02 or \x02!unrated\x02.')
			rs.append(u'Use \x02!rq unrated [<limit>]\x02 to add unrated songs (up '
				u'to <limit>) to your request queue, leave off <limit> to fill your '
				u'request queue.')
			rs.append(u'Use \x02!rq fav [<limit>]\x02 to add favourite songs to your '
				u'request queue.')
			rs.append(u'Use \x02!rq stash\x02 to remove all songs from your request '
				u'queue and stash them with wormgas (\'pause\' your request queue).')
			rs.append(u'Use \x02!rq loadstash\x02 to move songs from your stash to '
				u'your request queue (\'resume\' your request queue).')
			rs.append(u'Use \x02!rq showstash\x02 to see what is in your request '
				u'stash and \x02!rq clearstash\x02 to remove all songs from your '
				u'request stash.')
		elif topic == u'set':
			if is_admin:
				rs.append(u'Use \x02!set [<id>] [<value>]\x02 to display or change '
					u'configuration settings.')
				rs.append(u'Leave off <value> to see the current setting.')
				rs.append(u'Leave off <id> and <value> to see a list of all available '
					'config ids.')
			else:
				rs.append(notpermitted)
		elif topic == u'stats':
			rs.append(u'Use \x02!stats [<channel>]\x02 to show information about the '
				u'music collection, leave off <channel> to see the aggregate for all '
				u'channels.')
			rs.append(channelcodes)
		elif topic == u'stop':
			if is_admin:
				rs.append(u'Use \x02!stop\x02 to shut down the bot.')
			else:
				rs.append(notpermitted)
		elif topic == u'unrated':
			rs.append(u'Use \x02!unrated <channel> [<num>]\x02 to see songs you have '
				u'not rated, <num> can go up to 12, leave it off to see just one song.')
			rs.append(channelcodes)
		elif topic == u'unset':
			if is_admin:
				rs.append(u'Use \x02!unset <id>\x02 to remove a configuration setting.')
			else:
				rs.append(notpermitted)
		elif topic == u'ustats':
			rs.append(u'Use \x02!ustats [<nick>]\x02 to show user statistics for '
				'<nick>, leave off <nick> to see your own statistics.')
		elif topic in [u'vote', u'vt']:
			rs.append(u'Use \x02!vote <channel> <index>\x02 to vote in the current '
				u'election, find the <index> with \x02!election\x02.')
			rs.append(channelcodes)
		else:
			rs.append(u'I cannot help you with \'{}\''.format(topic))
			rs.append(wiki)

		output.privrs.extend(rs)

	@command_handler(u'!history(\s(?P<rchan>\w+))?')
	@command_handler(u'!hs(?P<rchan>\w+)?')
	def handle_history(self, nick, channel, output, rchan=None):
		'''Show the last several songs that played on the radio'''

		self.log.info(u'{} used !history'.format(nick))

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append(u'I cannot determine the channel.')
				self.handle_help(nick, channel, output, topic=u'history')
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic=u'history')
			return
		rchn = self.rw.channel_id_to_name(cid)

		for song in self.rwdb.get_history(cid):
			info = (rchn,) + song
			r = u'{}: {} -- {} [{}] / {} [{}]'.format(*info)
			output.privrs.append(r)

		output.privrs.reverse()

	@command_handler(u'^!id(\s(?P<mode>\w+))?(\s(?P<id>\d+))?')
	def handle_id(self, nick, channel, output, mode=None, id=None):
		'''Manage correlation between an IRC nick and Rainwave User ID

		Arguments:
			mode: string, one of 'add', 'drop', 'show'
			id: numeric, the person's Rainwave User ID'''

		self.log.info(u'{} used !id'.format(nick))

		# Make sure this nick is in the user_keys table
		self.config.store_nick(nick)

		if mode == u'add' and id:
			self.config.add_id_to_nick(id, nick)
			r = u'I assigned the user id {} to nick \'{}\'.'.format(id, nick)
			output.privrs.append(r)
		elif mode == u'drop':
			self.config.drop_id_for_nick(nick)
			r = u'I dropped the user id for nick \'{}\'.'.format(nick)
			output.privrs.append(r)
		elif mode == u'show':
			stored_id = self.config.get_id_for_nick(nick)
			if stored_id:
				r = u'The user id for nick \'{}\' is {}.'.format(nick, stored_id)
				output.privrs.append(r)
			else:
				r = u'I do not have a user id for nick \'{}\'.'.format(nick)
				output.privrs.append(r)
		else:
			self.handle_help(nick, channel, output, topic=u'id')

	@command_handler(u'^!key(\s(?P<mode>\w+))?(\s(?P<key>\w{10}))?')
	def handle_key(self, nick, channel, output, mode=None, key=None):
		'''Manage API keys

		Arguments:
			mode: string, one of 'add', 'drop', 'show'
			key: string, the API key to add'''

		self.log.info(u'{} used !key'.format(nick))

		# Make sure this nick is in the user_keys table
		self.config.store_nick(nick)

		if mode == u'add' and key:
			self.config.add_key_to_nick(key, nick)
			r = u'I assigned the API key \'{}\' to nick \'{}\'.'.format(key, nick)
			output.privrs.append(r)
		elif mode == u'drop':
			self.config.drop_key_for_nick(nick)
			r = u'I dropped the API key for nick \'{}\'.'.format(nick)
			output.privrs.append(r)
		elif mode == u'show':
			stored_id = self.config.get_key_for_nick(nick)
			if stored_id:
				r = u'The API key for nick \'{}\' is \'{}\'.'.format(nick, stored_id)
				output.privrs.append(r)
			else:
				r = u'I do not have an API key for nick \'{}\'.'.format(nick)
				output.privrs.append(r)
		else:
			self.handle_help(nick, channel, output, topic=u'key')

	@command_handler(u'^!lookup(\s(?P<rchan>\w+))?(\s(?P<mode>\w+))?'
		u'(\s(?P<text>.+))?')
	@command_handler(u'^!lu(?P<rchan>\w+)?(\s(?P<mode>\w+))?'
		u'(\s(?P<text>.+))?')
	def handle_lookup(self, nick, channel, output, rchan, mode, text):
		'''Look up (search for) a song or album'''

		self.log.info(u'{} used !lookup'.format(nick))

		if not self.rwdb:
			output.privrs.append(self.rwdberr)
			return

		if rchan in (u'song', u'album'):
			text = mode + u' ' + str(text)
			mode = rchan
			rchan = None

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append(u'I cannot determine the channel.')
				self.handle_help(nick, channel, output, topic=u'lookup')
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic=u'lookup')
			return
		rchn = self.rw.channel_id_to_name(cid)

		if mode == u'song':
			rows, unreported_results = self.rwdb.search_songs(cid, text)
			out = u'{rchan}: {album_name} / {song_title} [{song_id}]'
		elif mode == u'album':
			rows, unreported_results = self.rwdb.search_albums(cid, text)
			out = u'{rchan}: {album_name} [{album_id}]'
		else:
			self.handle_help(nick, channel, output, topic=u'lookup')
			return

		# If I got results, output them
		for row in rows:
			row[u'rchan'] = rchn
			output.privrs.append(out.format(**row))

		# If I had to trim the results, be honest about it
		if unreported_results > 0:
			r = u'{}: {} more result'.format(rchn, unreported_results)
			if unreported_results > 1:
				r += u's'
			r += u'. If you do not see what you are looking for, be more specific '
			r += u'with your search.'
			output.privrs.append(r)

			# If I did not find anything with this search, mention that
			if len(output.privrs) < 1:
				r = u'{}: No results.'.format(rchn)
				output.privrs.append(r)
			elif unreported_results < 1:
				# I got between 1 and 10 results
				num = len(output.privrs)
				r = u'{}: Your search returned {} result'.format(rchn, num)
				if num > 1:
					r += u's'
				r += u'.'
				output.privrs.insert(0, r)

	@command_handler(u'^!lstats(\s(?P<rchan>\w+))?(\s(?P<days>\d+))?')
	def handle_lstats(self, nick, channel, output, rchan=None, days=30):
		'''Reports listener statistics, as numbers or a chart

		Arguments:
			rchan: channel to ask about, or maybe 'chart'
			days: number of days to include data for chart'''

		self.log.info(u'{} used !lstats'.format(nick))

		if not self.rwdb:
			output.default.append(self.rwdberr)
			return

		rs = []

		if rchan:
			rchan = rchan.lower()

		cid = self.channel_ids.get(rchan, 0)
		rchn = self.rw.channel_id_to_name(cid)

		try:
			days = int(days)
		except TypeError:
			days = 30

		if rchan != u'chart':
			regd, guest = self.rwdb.get_listener_stats(cid)
			r = u'{}: {} registered users, '.format(rchn, regd)
			r += u'{} guests.'.format(guest)
			rs.append(r)
		elif rchan == u'chart':

			# Base url
			url = u'http://chart.apis.google.com/chart'

			# Axis label styles
			url += u'?chxs=0,676767,11.5,-1,l,676767'

			# Visible axes
			url += u'&chxt=y,x'

			# Bar width and spacing
			url += u'&chbh=a'

			# Chart size
			url += u'&chs=600x400'

			# Chart type
			url += u'&cht=bvs'

			# Series colors
			url += u'&chco=A2C180,3D7930,3399CC,244B95,FFCC33,FF9900,CC80ff,66407f,'
			url += u'900000,480000'

			# Chart legend text
			url += u'&chdl=Game+Guests|Game+Registered|OCR+Guests|OCR+Registered|'
			url += u'Covers+Guests|Covers+Registered|Chiptune+Guests|'
			url += u'Chiptune+Registered|All+Guests|All+Registered'

			# Chart title
			url += u'&chtt=Rainwave+Average+Hourly+Usage+by+User+Type+and+Channel|'
			url += u'{}+Day'.format(days)
			if days > 1:
				url += u's'
			url += u'+Ending+' + time.strftime(u'%Y-%m-%d', time.gmtime())

			game_g = []
			game_r = []
			ocr_g = []
			ocr_r = []
			cover_g = []
			cover_r = []
			chip_g = []
			chip_r = []
			all_g = []
			all_r = []
			for cid, guests, users in self.rwdb.get_listener_chart_data(days):
				if cid == 1:
					game_g.append(guests)
					game_r.append(users)
				elif cid == 2:
					ocr_g.append(guests)
					ocr_r.append(users)
				elif cid == 3:
					cover_g.append(guests)
					cover_r.append(users)
				elif cid == 4:
					chip_g.append(guests)
					chip_r.append(users)
				elif cid == 5:
					all_g.append(guests)
					all_r.append(users)

			lmax = sum((max(game_g), max(game_r), max(ocr_g), max(ocr_r),
				max(cover_g), max(cover_r), max(chip_g), max(chip_r),
				max(all_g), max(all_r)))
			lceil = math.ceil(lmax / 50) * 50

			# Chart data
			url += u'&chd=t:'
			url += u','.join([u'{}'.format(el) for el in game_g]) + u'|'
			url += u','.join([u'{}'.format(el) for el in game_r]) + u'|'
			url += u','.join([u'{}'.format(el) for el in ocr_g]) + u'|'
			url += u','.join([u'{}'.format(el) for el in ocr_r]) + u'|'
			url += u','.join([u'{}'.format(el) for el in cover_g]) + u'|'
			url += u','.join([u'{}'.format(el) for el in cover_r]) + u'|'
			url += u','.join([u'{}'.format(el) for el in chip_g]) + u'|'
			url += u','.join([u'{}'.format(el) for el in chip_r]) + u'|'
			url += u','.join([u'{}'.format(el) for el in all_g]) + u'|'
			url += u','.join([u'{}'.format(el) for el in all_r])

			# Axis ranges
			url += u'&chxr=0,0,{}|1,0,23'.format(lceil)

			# Scale for text format with custom range
			url += u'&chds='
			t1 = u'0,{}'.format(lceil)
			t2 = []
			for i in range(10):
				t2.append(t1)
			url += u','.join(t2)
			rs.append(self._shorten(url))
		else:
			self.handle_help(nick, channel, output, topic=u'lstats')
			return

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		ltls = int(self.config.get(u'lasttime:lstats', 0))
		wls = int(self.config.get(u'wait:lstats', 0))
		if ltls < time.time() - wls:
			output.default.extend(rs)
			self.config.set(u'lasttime:lstats', time.time())
		else:
			output.privrs.extend(rs)
			wait = ltls + wls - int(time.time())
			output.privrs.append(u'I am cooling down. You cannot use !lstats in '
				u'{} for another {} seconds.'.format(channel, wait))

	@command_handler(u'!newmusic(\s(?P<rchan>\w+))?')
	def handle_newmusic(self, nick, channel, output, rchan=None, force=True):
		'''Check for new music and announce up to three new songs per station'''

		r = u'Looking for new music on channel {}'.format(rchan)
		r += u', force is {}'.format(force)
		self.log.info(r)

		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !newmusic'.format(nick))
			return

		self.config.set(u'lasttime:musiccheck', time.time())

		if rchan:
			rchan = rchan.lower()

		if rchan in self.channel_ids:
			cid = self.channel_ids[rchan]
		else:
			self.handle_help(nick, channel, output, topic=u'newmusic')
			return

		rchn = self.rw.channel_id_to_name(cid)
		self.log.info(u'Looking for new music on the {}'.format(rchn))

		if force:
			self.config.unset(u'maxid:{}'.format(cid))

		maxid = self.config.get(u'maxid:{}'.format(cid), 0)
		self.log.info(u'Looking for music newer than {}'.format(maxid))

		if self.rwdb:
			newmaxid = self.rwdb.get_max_song_id(cid)
		else:
			output.privrs.append(self.rwdberr)
			return

		if newmaxid > int(maxid):
			songs = self.rwdb.get_new_song_info(cid)
			for r, url in songs:
				msg = u'New on the {}: {}'.format(rchn, r)
				if u'http' in url:
					msg += u' <{}>'.format(self._shorten(url))
				output.rs.append(msg)
			self.config.set(u'maxid:{}'.format(cid), newmaxid)

	@command_handler(u'!nowplaying(\s(?P<rchan>\w+))?')
	@command_handler(u'!np(?P<rchan>\w+)?')
	def handle_nowplaying(self, nick, channel, output, rchan=None):
		'''Report what is currently playing on the radio'''

		self.log.info(u'{} used !nowplaying'.format(nick))

		rs = []

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append(u'I cannot determine the channel.')
				self.handle_help(nick, channel, output, topic=u'nowplaying')
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids[rchan]
		else:
			self.handle_help(nick, channel, output, topic=u'nowplaying')
			return
		rchn = self.rw.channel_id_to_name(cid)

		data = self.rw.get_timeline(cid)
		sched_id = data[u'sched_current'][u'sched_id']
		sched_type = data[u'sched_current'][u'sched_type']
		if sched_type in (0, 4):
			np = data[u'sched_current'][u'song_data'][0]
			album = np[u'album_name']
			song = np[u'song_title']
			arts = np[u'artists']
			art_list = []
			for art in arts:
				art_name = art[u'artist_name']
				art_list.append(art_name)
			artt = u', '.join(art_list)
			r = u'Now playing on the '
			r += u'{}: {} / {} by {}'.format(rchn, album, song, artt)
			url = np[u'song_url']
			if url and u'http' in url:
				r += u' <{}>'.format(self._shorten(url))

			if u'elec_votes' in np:
				votes = np[u'elec_votes']
			else:
				votes = 0
			ratings = np[u'song_rating_count']
			avg = np[u'song_rating_avg']

			r += u' ({} vote'.format(votes)
			if votes != 1:
				r += u's'
			r += u', {} rating'.format(ratings)
			if ratings != 1:
				r += u's'
			r += u', rated {}'.format(avg)

			type = np[u'elec_isrequest']
			if type in (3, 4):
				r += u', requested by {song_requestor}'.format(**np)
			elif type in (0, 1):
				r += u', conflict'
			r += u')'
			rs.append(r)
		else:
			r = u'{}: I have no idea (sched_type = {})'.format(rchn, sched_type)
			rs.append(r)

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		if sched_id == int(self.config.get(u'np:{}'.format(cid), 0)):
			output.privrs.extend(rs)
			r = u'I am cooling down. You can only use !nowplaying in '
			r += u'{} once per song.'.format(channel)
			output.privrs.append(r)
		else:
			output.default.extend(rs)
			self.config.set(u'np:{}'.format(cid), sched_id)

	@command_handler(u'^!otp')
	def handle_otp(self, nick, channel, output):
		self.log.info(u'{} used !otp'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !otp'.format(nick))
			return

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		for o in self.rwdb.get_all_otps():
			r = u'{} [{}] {} / {}'.format(self.rw.channel_id_to_name(o[0]), *o[1:])
			output.default.append(r)

	@command_handler(u'^!ph (addalbum|aa) (?P<album_id>\d+)')
	def handle_ph_addalbum(self, nick, channel, output, album_id):
		'''Add all songs from an album to this user's Power Hour planning list'''

		self.log.info(u'{} used !ph addalbum'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		album_id = int(album_id)
		try:
			song_ids = self.rw.get_song_ids_in_album(album_id, **api_auth)
		except rainwave.RainwaveClientException as e:
			self.log.exception(e)
			output.privrs.append(str(e))
			return

		for song_id in song_ids:
			song_id = int(song_id)
			self.handle_ph_addsong(nick, channel, output, song_id)
		output.privrs.append(u'All done.')

	@command_handler(u'^!ph (addsong|add|as) (?P<song_id>\d+)')
	def handle_ph_addsong(self, nick, channel, output, song_id):
		'''Add a song to this user's Power Hour planning list'''

		self.log.info(u'{} used !ph addsong'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		song_id = int(song_id)
		m = self._get_song_info_string(song_id)

		if song_id in self.ph.items(nick):
			m += u' is already in your Power Hour planning list.'
		else:
			self.ph.add(nick, song_id)
			m += u' added to your Power Hour planning list.'

		output.privrs.append(m)

	@command_handler(u'^!ph (clear|cl)')
	def handle_ph_clear(self, nick, channel, output):
		'''Remove all songs from this user's Power Hour planning list'''

		self.log.info(u'{} used !ph clear'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		self.ph.clear(nick)
		output.privrs.append(u'Your Power Hour planning list has been cleared.')

	@command_handler(u'^!ph (down|dn) (?P<song_id>\d+)')
	def handle_ph_down(self, nick, channel, output, song_id):
		'''Move a song down in this user's Power Hour planning list'''

		self.log.info(u'{} used !ph down'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		song_id = int(song_id)
		m = self._get_song_info_string(song_id)

		if song_id in self.ph.items(nick):
			self.ph.down(nick, song_id)
			m += u' moved down in your Power Hour planning list.'
		else:
			m += u' is not in your Power Hour planning list'

		output.privrs.append(m)

	@command_handler(u'^!ph go (?P<rchan>\w+)')
	def handle_ph_go(self, nick, channel, output, rchan):
		'''Start a Power Hour on a channel using this user's Power Hour planning
		list'''

		self.log.info(u'{} used !ph go'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))

		if rchan in self.channel_ids:
			cid = self.channel_ids[rchan]
		else:
			output.privrs.append(u'{} is not a valid channel code.'.format(rchan))
			return

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		errors = 0
		for song_id in self.ph.items(nick):
			song_id = int(song_id)
			data = self.rw.add_one_time_play(cid, song_id, **api_auth)
			m = self._get_song_info_string(song_id) + u' // '
			if u'oneshot_add_result' in data:
				try:
					m += data[u'oneshot_add_result'][u'text']
				except UnicodeDecodeError:
					self.log.exception(u'Not again. :(')
			else:
				try:
					m += data[u'error'][u'text']
				except UnicodeDecodeError:
					self.log.exception(u'Not again. :(')
				errors += 1
			output.privrs.append(m)

		if errors == 0:
			self.handle_ph_clear(nick, channel, output)

	@command_handler(u'!ph (length|len)')
	def handle_ph_length(self, nick, channel, output):
		'''Show number of songs and total running time of this user's Power Hour
		planning list'''

		self.log.info(u'{} used !ph length'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		count = len(self.ph.items(nick))
		seconds = 0
		for song_id in self.ph.items(nick):
			info = self.rwdb.get_song_info(song_id)
			seconds += info[u'length']

		if count == 0:
			output.privrs.append(u'Your Power Hour planning list is empty.')
			return

		m = u'Your Power Hour planning list contains {} song'.format(count)
		if count > 1:
			m += u's'

		m += u' and will run for {}.'.format(self._get_readable_time_span(seconds))

		output.privrs.append(m)

	@command_handler(u'^!ph (list|ls)')
	def handle_ph_list(self, nick, channel, output):
		'''Show all songs in this user's Power Hour planning list'''

		self.log.info(u'{} used !ph list'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		count = 0
		for song_id in self.ph.items(nick):
			count += 1
			output.privrs.append(self._get_song_info_string(song_id))

		if count == 0:
			output.privrs.append(u'Your Power Hour planning list is empty.')
		else:
			output.privrs.append(u'All done.')

	@command_handler(u'^!ph pause (?P<rchan>\w+)')
	def handle_ph_pause(self, nick, channel, output, rchan):
		'''Remove scheduled one-time plays from channel and put them in this user's
		Power Hour planning list'''

		self.log.info(u'{} used !ph pause'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		if rchan in self.channel_ids:
			cid = self.channel_ids[rchan]
		else:
			output.privrs.append(u'{} is not a valid channel code.'.format(rchan))
			return

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		add_to_ph = []

		while True:
			data = self.rw.get_timeline(cid)
			otp_count = 0
			for event in data[u'sched_next']:
				if event[u'sched_type'] == 4:
					otp_count += 1
					song_id = int(event[u'song_data'][0][u'song_id'])
					if song_id in add_to_ph:
						continue
					m = self._get_song_info_string(song_id) + u' // '
					add_to_ph.append(song_id)
					sched_id = event[u'sched_id']
					d = self.rw.delete_one_time_play(cid, sched_id, **api_auth)
					if u'oneshot_delete_result' in d:
						m += d[u'oneshot_delete_result'][u'text']
					else:
						m += d[u'error'][u'text']
					output.privrs.append(m)
			if otp_count == 0:
				break

		if len(add_to_ph) > 0:
			add_to_ph.extend(self.ph.items(nick))
			self.ph.set(nick, add_to_ph)
			output.privrs.append(u'All done.')
		else:
			m = u'No One-Time Plays scheduled on the {}.'
			output.privrs.append(m.format(self.rw.channel_id_to_name(cid)))

	@command_handler(u'^!ph (removealbum|ra) (?P<album_id>\d+)')
	def handle_ph_removealbum(self, nick, channel, output, album_id):
		'''Remove all songs in an album from this user's Power Hour planning list'''

		self.log.info(u'{} used !ph removealbum'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		album_id = int(album_id)
		try:
			song_ids = self.rw.get_song_ids_in_album(album_id, **api_auth)
		except rainwave.RainwaveClientException as e:
			self.log.exception(e)
			output.privrs.append(str(e))
			return

		for song_id in song_ids:
			song_id = int(song_id)
			self.handle_ph_removesong(nick, channel, output, song_id)
		output.privrs.append(u'All done.')

	@command_handler(u'^!ph (remove|rm|removesong|rs) (?P<song_id>\d+)')
	def handle_ph_removesong(self, nick, channel, output, song_id):
		'''Remove a song from this user's Power Hour planning list'''

		self.log.info(u'{} used !ph removesong'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		song_id = int(song_id)
		m = self._get_song_info_string(song_id)

		if song_id in self.ph.items(nick):
			self.ph.remove(nick, song_id)
			m += u' removed from your Power Hour planning list.'
		else:
			m += u' is not in your Power Hour planning list.'

		output.privrs.append(m)

	@command_handler(u'^!ph up (?P<song_id>\d+)')
	def handle_ph_up(self, nick, channel, output, song_id):
		'''Move a song up in this user's Power Hour planning list'''

		self.log.info(u'{} used !ph up'.format(nick))
		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !ph'.format(nick))
			return

		if self.rwdb is None:
			output.privrs.append(self.rwdberr)
			return

		song_id = int(song_id)
		m = self._get_song_info_string(song_id)

		if song_id in self.ph.items(nick):
			self.ph.up(nick, song_id)
			m += u' moved up in your Power Hour planning list.'
		else:
			m += u' is not in your Power Hour planning list.'

		output.privrs.append(m)

	@command_handler(u'!prevplayed(\s(?P<rchan>\w+))?(\s(?P<index>\d))?')
	@command_handler(u'!pp(?P<rchan>\w+)?(\s(?P<index>\d))?')
	def handle_prevplayed(self, nick, channel, output, rchan=None, index=0):
		'''Report what was previously playing on the radio

		Arguments:
			station: station to check
			index: (int) (0, 1, 2) which previously played song, higher number =
				further in the past'''

		self.log.info(u'{} used !prevplayed'.format(nick))

		rs = []

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append(u'I cannot determine the channel')
				self.handle_help(nick, channel, output, topic=u'prevplayed')
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic=u'prevplayed')
			return
		rchn = self.rw.channel_id_to_name(cid)

		try:
			index = int(index)
		except TypeError:
			index = 0
		if index not in [0, 1, 2]:
			self.handle_help(nick, channel, output, topic=u'prevplayed')
			return

		data = self.rw.get_timeline(cid)
		sched_id = data[u'sched_history'][index][u'sched_id']
		sched_type = data[u'sched_history'][index][u'sched_type']
		if sched_type in (0, 4):
			pp = data[u'sched_history'][index][u'song_data'][0]
			album = pp[u'album_name']
			song = pp[u'song_title']
			arts = pp[u'artists']
			art_list = []
			for art in arts:
				art_name = art[u'artist_name']
				art_list.append(art_name)
			artt = u', '.join(art_list)
			r = u'Previously on the {}: {} / {} by {}'.format(rchn, album, song, artt)

			if u'elec_votes' in pp:
				votes = pp[u'elec_votes']
			else:
				votes = 0
			avg = pp[u'song_rating_avg']

			r += u' ({} vote'.format(votes)
			if votes != 1:
				r += u's'
			r += u', rated {}'.format(avg)

			type = pp[u'elec_isrequest']
			if type in (3, 4):
				r += u', requested by {song_requestor}'.format(**pp)
			elif type in (0, 1):
				r += u', conflict'
			r += u')'
			rs.append(r)
		else:
			r = u'{}: I have no idea (sched_type = {})'.format(rchn, sched_type)
			rs.append(r)

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		if sched_id == int(self.config.get(u'pp:{}:{}'.format(cid, index), 0)):
			output.privrs.extend(rs)
			r = u'I am cooling down. You can only use !prevplayed in '
			r += u'{} once per song.'.format(channel)
			output.privrs.append(r)
		else:
			output.default.extend(rs)
			self.config.set(u'pp:{}:{}'.format(cid, index), sched_id)

	@command_handler(u'^!rate(\s(?P<rchan>\S+))?(\s(?P<rating>\S+))?')
	@command_handler(u'^!rt(?P<rchan>\S+)?(\s(?P<rating>\S+))?')
	def handle_rate(self, nick, channel, output, rchan=None, rating=None):
		'''Rate the currently playing song

		Arguments:
			rchan: station of song to rate
			rating: the rating'''

		self.log.info(u'{} used !rate'.format(nick))

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		if rating is None:
			rating = rchan
			rchan = None

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append(u'I cannot determine the channel.')
				self.handle_help(nick, channel, output, topic=u'rate')
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic=u'prevplayed')
			return

		# Get the song_id
		data = self.rw.get_timeline(cid)
		song_id = data[u'sched_current'][u'song_data'][0][u'song_id']

		# Try the rate
		data = self.rw.rate(cid, song_id, rating, **api_auth)

		if u'rate_result' in data:
			output.privrs.append(data[u'rate_result'][u'text'])
		else:
			output.privrs.append(data[u'error'][u'text'])

	@command_handler(u'^!refresh(\s(?P<rchan>\w+))?')
	def handle_refresh(self, nick, channel, output, rchan=None):
		'''See the status of or initiate a playlist refresh'''

		self.log.info(u'{} used !refresh'.format(nick))

		if not self._is_admin(nick):
			self.log.warning(u'{} does not have privs to use !refresh'.format(nick))
			return

		# This command requires the Rainwave database

		if self.rwdb is None:
			output.privrs.append(u'The Rainwave database is unavailable.')
			return

		if rchan:
			rchan = rchan.lower()

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
			self.rwdb.request_playlist_refresh(cid)

		for pending in self.rwdb.get_pending_refresh_jobs():
			m = u'Pending playlist refresh on the {}.'
			output.privrs.append(m.format(self.rw.channel_id_to_name(pending)))

		for running in self.rwdb.get_running_refresh_jobs():
			m = u'Running playlist refresh on the {}.'
			channel_name = self.rw.channel_id_to_name(self.channel_ids.get(running))
			output.privrs.append(m.format(channel_name))

		if len(output.privrs) == 0:
			output.privrs.append(u'No pending or running playlist refresh jobs.')

	@command_handler(u'!restart')
	def handle_restart(self, nick, channel, output):
		'''Restart the bot'''

		self.log.info(u'{} used !restart'.format(nick))

		if self._is_admin(nick):
			self.config.set(u'restart_on_stop', 1)
			self.handle_stop(nick, channel, output)
		else:
			self.log.warning(u'{} does not have privs to use !restart'.format(nick))

	@command_handler(u'!roll(\s(?P<dice>\d+)(d(?P<sides>\d+))?)?')
	def handle_roll(self, nick, channel, output, dice=None, sides=None):
		'''Roll some dice'''

		self.log.info(u'{} used !roll'.format(nick))

		try:
			dice = min(int(dice), 100)
		except TypeError:
			dice = 1

		try:
			sides = max(min(int(sides), 100), 1)
		except TypeError:
			sides = 20

		rolls = []
		for i in range(dice):
			rolls.append(random.randint(1, sides))

		r = u'{}d{}: '.format(dice, sides)
		if dice > 1 and dice < 11:
			r += u'[' + u', '.join(map(str, rolls)) + u'] = '
		r += u'{}'.format(sum(rolls))

		if channel == PRIVMSG:
			output.default.append(r)
			return

		ltr = int(self.config.get(u'lasttime:roll', 0))
		wr = int(self.config.get(u'wait:roll', 0))
		if ltr < time.time() - wr:
			output.default.append(r)
			self.config.set(u'lasttime:roll', time.time())
		else:
			output.privrs.append(r)
			wait = ltr + wr - int(time.time())
			r = u'I am cooling down. You cannot use !roll in '
			r += u'{} for another {} seconds.'.format(channel, wait)
			output.privrs.append(r)

	@command_handler(u'!(?P<mode>rock|paper|scissors)')
	def handle_rps(self, nick, channel, output, mode=None):
		'''Rock, paper, scissors'''

		if mode is None:
			return
		else:
			mode = mode.lower()

		self.log.info(u'{} used !{}'.format(nick, mode))

		rps = [u'rock', u'paper', u'scissors']
		challenge = rps.index(mode)
		response = random.randint(0, 2)

		self.config.log_rps(nick, challenge, response)

		r = u'You challenge with {}. I counter with {}. '.format(mode, rps[response])

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
			output.default.append(r)
			return

		ltr = int(self.config.get(u'lasttime:rps', 0))
		wr = int(self.config.get(u'wait:rps', 0))
		if ltr < time.time() - wr:
			output.default.append(r)
			self.config.set(u'lasttime:rps', time.time())
		else:
			output.privrs.append(r)
			wait = ltr + wr - int(time.time())
			r = u'I am cooling down. You cannot use !{} in {} '.format(mode, channel)
			r += u'for another {} seconds.'.format(wait)
			output.privrs.append(r)

	@command_handler(u'^!rps record(\s(?P<target>\S+))?')
	def handle_rps_record(self, nick, channel, output, target=None):
		'''Report RPS record for a nick'''

		self.log.info(u'{} used !rps record'.format(nick))

		if target is None:
			target = nick

		w, d, l = self.config.get_rps_record(target)
		total = sum((w, d, l))
		r = u'RPS record for {} ({} game'.format(target, total)
		if total != 1:
			r += u's'
		r += u') is {}-{}-{} (w-d-l).'.format(w, d, l)

		if channel == PRIVMSG:
			output.default.append(r)
			return

		ltr = int(self.config.get(u'lasttime:rps', 0))
		wr = int(self.config.get(u'wait:rps', 0))
		if ltr < time.time() - wr:
			output.default.append(r)
			self.config.set(u'lasttime:rps', time.time())
		else:
			output.privrs.append(r)
			wait = ltr + wr - int(time.time())
			m = u'I am cooling down. You cannot use !rps in '
			m += u'{} for another {} seconds.'.format(channel, wait)
			output.privrs.append(m)

	@command_handler(u'!rps rename(\s(?P<old>\S+))?(\s(?P<new>\S+))?')
	def handle_rps_rename(self, nick, channel, output, old=None, new=None):
		'''Rename an RPS nick, useful for merging game histories'''

		self.log.info(u'{} used !rps rename'.format(nick))

		if self._is_admin(nick) and old and new:
			self.config.rename_rps_player(old, new)
			r = u'I assigned the RPS game history for {} to {}.'.format(old, new)
			output.privrs.append(r)

	@command_handler(u'^!rps reset')
	def handle_rps_reset(self, nick, channel, output):
		'''Reset RPS stats and delete game history for a nick'''

		self.log.info(u'{} used !rps reset'.format(nick))

		self.config.reset_rps_record(nick)
		r = u'I reset your RPS record and deleted your game history.'
		output.privrs.append(r)

	@command_handler(u'!rps stats(\s(?P<target>\S+))?')
	def handle_rps_stats(self, nick, channel, output, target=None):
		'''Get some RPS statistics for a player'''

		self.log.info(u'{} used !rps stats'.format(nick))

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
			output.default.append(r)
			return

		ltr = int(self.config.get(u'lasttime:rps', 0))
		wr = int(self.config.get(u'wait:rps', 0))
		if ltr < time.time() - wr:
			output.default.append(r)
			self.config.set(u'lasttime:rps', time.time())
		else:
			output.privrs.append(r)
			wait = ltr + wr - int(time.time())
			r = u'I am cooling down. You cannot use !rps in {} '.format(channel)
			r += u'for another {} seconds.'.format(wait)
			output.privrs.append(r)

	@command_handler(u'^!rps who')
	def handle_rps_who(self, nick, channel, output):
		'''List all players in the RPS game history'''

		self.log.info(u'{} used !rps who'.format(nick))

		rs = []
		players = self.config.get_rps_players()

		mlnl = int(self.config.get(u'maxlength:nicklist', 10))
		while len(players) > mlnl:
			plist = players[:mlnl]
			players[:mlnl] = []
			r = u'RPS players: ' + u', '.join(plist)
			rs.append(r)
		r = u'RPS players: ' + u', '.join(players)
		rs.append(r)

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		ltr = int(self.config.get(u'lasttime:rps', 0))
		wr = int(self.config.get(u'wait:rps', 0))
		if ltr < time.time() - wr:
			output.default.extend(rs)
			self.config.set(u'lasttime:rps', time.time())
		else:
			output.privrs.extend(rs)
			wait = ltr + wr - int(time.time())
			r = u'I am cooling down. You cannot use !rps in {} '.format(channel)
			r += u'for another {} seconds.'.format(wait)
			output.privrs.append(r)

	@command_handler(u'^!rq (?P<song_id>\d+)')
	def handle_rq(self, nick, channel, output, song_id):
		'''Add a song to your request queue'''

		self.log.info(u'{} used !rq'.format(nick))

		# detect radio channel, return if not tuned in
		radio_channel_id = self._get_current_channel_for_nick(nick)
		if radio_channel_id is None:
			output.privrs.append(u'You must be tuned in to request')
			return
		radio_channel_id = int(radio_channel_id)

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		song_id = int(song_id)
		song_info = self._get_song_info_string(song_id)
		output.privrs.append(u'Attempting request: {}'.format(song_info))

		data = self.rw.request(radio_channel_id, song_id, **api_auth)
		if u'request_result' in data:
			output.privrs.append(data[u'request_result'][u'text'])
		else:
			output.privrs.append(data[u'error'][u'text'])

	@command_handler(u'^!rq clearstash$')
	def handle_rq_clearstash(self, nick, channel, output):
		'''Clear a user's request stash'''

		self.log.info(u'{} used !rq clearstash'.format(nick))
		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return

		self.rq.clear(str(api_auth[u'user_id']))
		output.privrs.append(u'I cleared your request stash.')

	@command_handler(u'^!rq fav(\s(?P<limit>\d+))?')
	def handle_rq_fav(self, nick, channel, output, limit=None):
		'''Request favourite songs up to limit'''

		self.log.info(u'{} used !rq fav'.format(nick))

		if self.rwdb is None:
			output.privrs.append(u'The Rainwave database is unavailable.')
			return

		# detect radio channel, return if not tuned in
		radio_channel_id = self._get_current_channel_for_nick(nick)
		if radio_channel_id is None:
			output.privrs.append(u'You must be tuned in to request')
			return
		radio_channel_id = int(radio_channel_id)

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		if limit is None:
			limit = self.config.get(u'maxlength:unrated', 12)
		limit = int(limit)

		favourite = self.rwdb.get_fav_songs(api_auth[u'user_id'], radio_channel_id)

		if len(favourite) == 0:
			output.privrs.append(u'No favourite songs.')
			return

		i = 0
		while i < limit and i < int(self.config.get(u'maxlength:unrated', 12)):
			if len(favourite) > 0:
				song_id = favourite.pop(0)
			else:
				output.privrs.append(u'No more albums with favourite songs.')
				return
			song_info = self._get_song_info_string(song_id)
			output.privrs.append(u'Attempting request: {}'.format(song_info))
			data = self.rw.request(radio_channel_id, song_id, **api_auth)
			if u'request_result' in data:
				if data[u'request_result'][u'code'] == 1:
					output.privrs.append(data[u'request_result'][u'text'])
					i += 1
				elif data[u'request_result'][u'code'] == -6:
					output.privrs.append(data[u'request_result'][u'text'])
					return
				else:
					fail = data[u'request_result'][u'text']
					output.privrs.append(u'Request failed. ({})'.format(fail))
			else:
				output.privrs.append(data[u'error'][u'text'])
				output.privrs.append(u'I ran into a problem. I will stop here.')
				return

		output.privrs.append(u'All done.')

	@command_handler(u'^!rq loadstash$')
	def handle_rq_loadstash(self, nick, channel, output):
		'''Load a user's request stash into his radio request queue'''

		self.log.info(u'{} used !rq loadstash'.format(nick))

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		stash = self.rq.items(str(api_auth[u'user_id']))[:]
		if len(stash) < 1:
			output.privrs.append(u'Your request stash is empty.')
			return

		radio_channel_id = self._get_current_channel_for_nick(nick)
		if radio_channel_id is None:
			output.privrs.append(u'You must be tuned in to request.')
			return
		radio_channel_id = int(radio_channel_id)

		for song_id in stash:
			song_id = int(song_id)
			song_info = self._get_song_info_string(song_id)
			output.privrs.append(u'Attempting request: {}'.format(song_info))
			data = self.rw.request(radio_channel_id, song_id, **api_auth)
			if u'request_result' in data:
				output.privrs.append(data[u'request_result'][u'text'])
				if data[u'request_result'][u'code'] == 1:
					output.privrs.append(u'Removing from stash: {}'.format(song_info))
					self.rq.remove(str(api_auth[u'user_id']), song_id)
				else:
					m = u'I ran into a problem. I will stop here and leave the rest of '
					m += u'your stash intact.'
					output.privrs.append(m)
					return
			else:
				output.privrs.append(data[u'error'][u'text'])
				m = u'I ran into a problem. I will stop here and leave the rest of '
				m += u'your stash intact.'
				output.privrs.append(m)
				return
		output.privrs.append(u'All done.')

	@command_handler(u'^!rq showstash$')
	def handle_rq_showstash(self, nick, channel, output):
		'''Show what is in a user's rq stash'''

		self.log.info(u'{} used !rq showstash')

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return

		count = len(self.rq.items(str(api_auth[u'user_id'])))
		if count > 0:
			if count == 1:
				m = u'There is 1 song in your request stash.'
			else:
				m = u'There are {} songs in your request stash.'.format(count)
			output.privrs.append(m)
			for song_id in self.rq.items(str(api_auth[u'user_id'])):
				output.privrs.append(self._get_song_info_string(song_id))
		else:
			output.privrs.append(u'Your request stash is empty.')

	@command_handler(u'^!rq stash$')
	def handle_rq_stash(self, nick, channel, output):
		'''Pull a user's requests from the radio and stash locally'''

		self.log.info(u'{} used !rq stash'.format(nick))

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		self.rq.clear(str(api_auth[u'user_id']))
		data = self.rw.get_requests(**api_auth)
		for request in data[u'requests_user']:
			self.rq.add(str(api_auth[u'user_id']), request[u'song_id'])
			self.rw.delete_request(request[u'requestq_id'], **api_auth)

		request_count = len(data[u'requests_user'])
		if request_count > 0:
			m = u'I stashed {} request'.format(request_count)
			if request_count > 1:
				m += u's'
			m += u' and cleared your radio request queue. Use \x02!rq loadstash\x02 '
			m += u'to load the stash into your request queue.'
		else:
			m = u'Your radio request queue is empty.'

		output.privrs.append(m)

	@command_handler(u'^!rq unrated(\s(?P<limit>\d+))?')
	def handle_rq_unrated(self, nick, channel, output, limit=None):
		'''Request unrated songs up to limit'''

		self.log.info(u'{} used !rq unrated'.format(nick))

		if self.rwdb is None:
			output.privrs.append(u'The Rainwave database is unavailable.')
			return

		# detect radio channel, return if not tuned in
		radio_channel_id = self._get_current_channel_for_nick(nick)
		if radio_channel_id is None:
			output.privrs.append(u'You must be tuned in to request')
			return
		radio_channel_id = int(radio_channel_id)

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		if limit is None:
			limit = self.config.get(u'maxlength:unrated', 12)
		limit = int(limit)

		unrated = self.rwdb.get_unrated_songs(api_auth[u'user_id'], radio_channel_id)

		if len(unrated) == 0:
			output.privrs.append(u'No unrated songs.')
			return

		i = 0
		while i < limit and i < int(self.config.get(u'maxlength:unrated', 12)):
			if len(unrated) > 0:
				song_id = unrated.pop(0)
			else:
				output.privrs.append(u'No more albums with unrated songs.')
				return
			song_info_string = self._get_song_info_string(song_id)
			output.privrs.append(u'Attempting request: {}'.format(song_info_string))
			data = self.rw.request(radio_channel_id, song_id, **api_auth)
			if u'request_result' in data:
				if data[u'request_result'][u'code'] == 1:
					output.privrs.append(data[u'request_result'][u'text'])
					i += 1
				elif data[u'request_result'][u'code'] == -6:
					output.privrs.append(data[u'request_result'][u'text'])
					return
				else:
					failure_text = data[u'request_result'][u'text']
					output.privrs.append(u'Request failed. ({})'.format(failure_text))
			else:
				output.privrs.append(data[u'error'][u'text'])
				output.privrs.append(u'I ran into a problem. I will stop here.')
				return

		output.privrs.append(u'All done.')

	@command_handler(u'^!set(\s(?P<id>\S+))?(\s(?P<value>.+))?')
	def handle_set(self, nick, channel, output, id=None, value=None):
		'''View and set bot configuration'''

		self.log.info(u'{} used !set'.format(nick))

		if self._is_admin(nick):
			output.privrs.extend(self.config.handle(id, value))
		else:
			self.log.warning(u'{} does not have privs to use !set'.format(nick))
			self.handle_help(nick, channel, output, topic=u'set')

	@command_handler(u'!stats(\s(?P<rchan>\w+))?')
	def handle_stats(self, nick, channel, output, rchan=None):
		'''Report radio statistics'''

		self.log.info(u'{} used !stats'.format(nick))

		if rchan:
			rchan = rchan.lower()

		cid = self.channel_ids.get(rchan, 0)
		if self.rwdb:
			songs, albums, hours = self.rwdb.get_radio_stats(cid)
			r = u'{}: {} songs in {} albums with {} hours of music.'
			r = r.format(self.rw.channel_id_to_name(cid), songs, albums, hours)
		else:
			r = u'The Rainwave database is unavailable.'

		if channel == PRIVMSG:
			output.default.append(r)
			return

		lts = int(self.config.get(u'lasttime:stats', 0))
		ws = int(self.config.get(u'wait:stats', 0))
		if lts < time.time() - ws:
			output.default.append(r)
			self.config.set(u'lasttime:stats', time.time())
		else:
			output.privrs.append(r)
			wait = lts + ws - int(time.time())
			r = u'I am cooling down. You cannot use !stats in '
			r += u'{} for another {} seconds.'.format(channel, wait)
			output.privrs.append(r)

	@command_handler(u'!stop')
	def handle_stop(self, nick, channel, output):
		'''Shut down the bot'''

		self.log.info(u'{} used !stop'.format(nick))

		if self._is_admin(nick):
			if self.config.get(u'restart_on_stop'):
				self.config.unset(u'restart_on_stop')
				pid = subprocess.Popen([_abspath, u'5'], stdout=subprocess.PIPE,
					stderr=subprocess.PIPE, stdin=subprocess.PIPE)
			self.die(u'I was stopped by {}'.format(nick))
		else:
			self.log.warning(u'{} does not have privs to use !stop'.format(nick))

	@command_handler(u'!unrated(\s(?P<rchan>\w+))?(\s(?P<num>\d+))?')
	def handle_unrated(self, nick, channel, output, rchan=None, num=None):
		'''Report unrated songs'''

		self.log.info(u'{} used !unrated'.format(nick))

		if rchan is None:
			self.handle_help(nick, channel, output, topic=u'unrated')
			return
		else:
			rchan = rchan.lower()

		if rchan not in self.channel_ids:
			if num is None:
				num = rchan
			luid = self.config.get_id_for_nick(nick)
			if not luid and self.rwdb:
				luid = self.rwdb.get_id_for_nick(nick)
			cur_cid = self.rwdb.get_current_channel(luid)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				self.handle_help(nick, channel, output, topic=u'unrated')
				return

		cid = self.channel_ids.get(rchan)

		try:
			num = int(num)
		except:
			num = 1

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return

		if self.rwdb is None:
			output.privrs.append(u'The Rainwave database is unavailable.')
			return

		unrated = self.rwdb.get_unrated_songs(api_auth[u'user_id'], cid)

		if len(unrated) == 0:
			output.privrs.append(u'No unrated songs.')
			return

		i = 0
		while i < num and i < int(self.config.get(u'maxlength:unrated')):
			if len(unrated) > 0:
				song_id = unrated.pop(0)
			else:
				output.privrs.append(u'No more albums with unrated songs.')
				return
			output.privrs.append(self._get_song_info_string(song_id))
			i += 1

		albums_left = len(unrated)
		if albums_left > 0:
			m = u'{} more album'.format(albums_left)
			if albums_left > 1:
				m += u's'
			m += u' with unrated songs.'
			output.privrs.append(m)

	@command_handler(u'^!unset(\s(?P<id>\S+))?')
	def handle_unset(self, nick, channel, output, id=None):
		'''Unset a configuration item'''

		self.log.info(u'{} used !unset'.format(nick))

		if self._is_admin(nick):
			if id:
				self.config.unset(id)
				output.privrs.append(u'{} has been unset.'.format(id))
				return
		else:
			self.log.warning(u'{} does not have privs to use !unset'.format(nick))

		self.handle_help(nick, channel, output, topic=u'unset')

	@command_handler(u'!ustats(\s(?P<target>.+))?')
	def handle_ustats(self, nick, channel, output, target=None):
		'''Report user statistics'''

		self.log.info(u'{} used !ustats'.format(nick))

		rs = []

		if target is None:
			target = nick

		api_auth = self._get_api_auth_for_nick(target)
		if u'user_id' not in api_auth:
			m = u'I do not recognize the username \'{}\'.'.format(target)
			output.default.append(m)
			return

		uid = self.config.get(u'api:user_id', 0)
		key = self.config.get(u'api:key', 0)
		data = self.rw.get_listener(api_auth[u'user_id'], uid, key)

		if u'listener_detail' in data:
			ld = data[u'listener_detail']
			cun = ld[u'username']  # canonical username

			# Line 1: winning/losing votes/requests

			wvotes = ld[u'radio_winningvotes']
			lvotes = ld[u'radio_losingvotes']
			wreqs = ld[u'radio_winningrequests']
			lreqs = ld[u'radio_losingrequests']
			tvotes = ld[u'radio_2wkvotes']
			r = u'{} has {} winning vote'.format(cun, wvotes)
			if wvotes != 1:
				r += u's'
			r += u', {} losing vote'.format(lvotes)
			if lvotes != 1:
				r += u's'
			r += u', {} winning request'.format(wreqs)
			if wreqs != 1:
				r += u's'
			r += u', {} losing request'.format(lreqs)
			if lreqs != 1:
				r += u's'
			r += u' ({} vote'.format(tvotes)
			if tvotes != 1:
				r += u's'
			r += u' in the last two weeks).'
			rs.append(r)

			# Line 2: rating progress

			game = ld[u'user_station_specific'][u'1'][u'rating_progress']
			ocr = ld[u'user_station_specific'][u'2'][u'rating_progress']
			cover = ld[u'user_station_specific'][u'3'][u'rating_progress']
			chip = ld[u'user_station_specific'][u'4'][u'rating_progress']
			r = u'{} has rated {:.0f}% of Game'.format(cun, game)
			r += u', {:.0f}% of OCR, {:.0f}% of Covers'.format(ocr, cover)
			r += u', {:.0f}% of Chiptune channel content.'.format(chip)
			rs.append(r)

			# Line 3: What channel are you listening to?

			cur_cid = self.rwdb.get_current_channel(api_auth[u'user_id'])
			if cur_cid:
				rch = self.rw.channel_id_to_name(cur_cid)
				r = u'{} is currently listening to the {}.'.format(cun, rch)
				rs.append(r)
		else:
			rs.append(data[u'error'][u'text'])

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		ltu = int(self.config.get(u'lasttime:ustats', 0))
		wu = int(self.config.get(u'wait:ustats', 0))
		if ltu < time.time() - wu:
			output.default.extend(rs)
			self.config.set(u'lasttime:ustats', time.time())
		else:
			output.privrs.extend(rs)
			wait = ltu + wu - int(time.time())
			r = u'I am cooling down. You cannot use !ustats in '
			r += u'{} for another {} seconds.'.format(channel, wait)
			output.privrs.append(r)

	@command_handler(u'!vote(\s(?P<rchan>\w+))?(\s(?P<index>\d+))?')
	@command_handler(u'!vt(?P<rchan>\w+)?(\s(?P<index>\d+))?')
	def handle_vote(self, nick, channel, output, rchan=None, index=None):
		'''Vote in the current election'''

		self.log.info(u'{} used !vote'.format(nick))

		if rchan is None:
			if index is None:
				self.handle_help(nick, channel, output, topic=u'vote')
				return
			rchan = 0
		else:
			rchan = rchan.lower()
			if index is None:
				index = rchan

		if rchan not in self.channel_ids:
			cur_cid = None
			if self.rwdb:
				luid = self.config.get_id_for_nick(nick)
				if not luid:
					luid = self.rwdb.get_id_for_nick(nick)
				cur_cid = self.rwdb.get_current_channel(luid)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append(u'Either you are not tuned in or your IRC '
					u'nick does not match your forum username. Tune in to a '
					u'channel or link your Rainwave account to this IRC nick '
					u'using \x02!id\x02.')
				return

		cid = self.channel_ids.get(rchan)

		try:
			index = int(index)
		except:
			self.handle_help(nick, channel, output, topic=u'vote')
			return

		if index not in [1, 2, 3]:
			self.handle_help(nick, channel, output, topic=u'vote')
			return

		api_auth = self._get_api_auth_for_nick(nick)
		if u'user_id' not in api_auth:
			output.privrs.append(self.missing_user_id)
			return
		if u'key' not in api_auth:
			output.privrs.append(self.missing_key)
			return

		# Get the elec_entry_id

		data = self.rw.get_timeline(cid)
		voteindex = index - 1
		song_data = data[u'sched_next'][0][u'song_data']
		elec_entry_id = song_data[voteindex][u'elec_entry_id']

		# Try the vote

		data = self.rw.vote(cid, elec_entry_id, **api_auth)

		if data[u'vote_result']:
			output.privrs.append(data[u'vote_result'][u'text'])
		else:
			output.privrs.append(data[u'error'][u'text'])

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
		msg = e.arguments[0].strip()

		rs = []
		privrs = []

		# Try all the command handlers

		output = Output(u'private')
		for command in _commands:
			if command(self, nick, msg, PRIVMSG, output):
				rs = output.rs
				privrs = output.privrs
				break

		if len(rs) + len(privrs) == 0:
			# No responses from the commands, punt to the brain

			privrs.extend(self._talk(msg))

		# Send responses

		channel = self.config.get(u'irc:channel')
		for r in rs:
			self._to_irc(c, u'privmsg', channel, r)

		for privr in privrs:
			self._to_irc(c, u'privmsg', nick, privr)

	def on_pubmsg(self, c, e):
		'''This method is called when a message is sent to the channel the bot
		is on

		Arguments:
			c: the Connection object associated with this event
			e: the Event object'''

		nick = e.source.nick
		chan = e.target
		msg = e.arguments[0].strip()

		rs = []
		privrs = []

		# Try all the command handlers

		output = Output(u'public')
		for command in _commands:
			if command(self, nick, msg, chan, output):
				rs = output.rs
				privrs = output.privrs
				break

		# If there are no responses from the commands, look for URLs

		if len(rs) + len(privrs) == 0:
			urls = self._find_urls(msg)
			for url in urls:
				title = None
				try:
					title = self.tf.get_title(url)
				except util.TitleFetcherError as e:
					self.log.exception(e)
				if title:
					self.log.info(u'Found a title: {}'.format(title))
					rs.append(u'[ {} ]'.format(title))

		# If there are no URLs, punt to the brain

		if len(rs) + len(privrs) == 0:
			talkrs = self._talk(msg)
			if len(talkrs) > 0:
				self.config.set(u'msg:last', msg)
				self.config.set(u'lasttime:msg', time.time())
				ltr = int(self.config.get(u'lasttime:respond', 0))
				wr = int(self.config.get(u'wait:respond', 0))

				if self.config.get(u'irc:nick') in msg:
					if time.time() > ltr + wr:
						rs.extend(talkrs)
						self.config.set(u'msg:last', talkrs[0])
						self.config.set(u'lasttime:respond', time.time())
					else:
						privrs.extend(talkrs)
						wait = ltr + wr - int(time.time())
						r = u'I am cooling down. I cannot respond in '
						r += u'{} for another {} seconds.'.format(chan, wait)
						privrs.append(r)

		# Send responses

		for r in rs:
			r = u'{}: {}'.format(nick, r)
			self._to_irc(c, u'privmsg', chan, r)

		for privr in privrs:
			self._to_irc(c, u'privmsg', nick, privr)

	def on_topic(self, c, e):
		'''This method is called when the topic is set

		Arguments:
			c: the Connection object associated with this event
			e: the Event object'''

		nick = e.source.nick
		new_topic = e.arguments[0]
		m = u'{} changed the topic to: {}'.format(nick, new_topic)

		nicks_to_match = self.config.get(u'funnytopic:nicks', u'').split()
		if nick in nicks_to_match:
			forum_id = self.config.get(u'funnytopic:forum_id')
			if forum_id is None:
				self.log.warning(u'Please !set funnytopic:forum_id')
				return
			topic_id = self.config.get(u'funnytopic:topic_id')
			if topic_id is None:
				self.log.warning(u'Please !set funnytopic:topic_id')
				return
			self._post_to_forum(forum_id, topic_id, m)

	def on_welcome(self, c, e):
		'''This method is called when the bot first connects to the server

		Arguments:
			c: the Connection object associated with this event
			e: the Event object'''

		passwd = self.config.get(u'irc:nickservpass')
		if passwd is not None:
			self._to_irc(c, u'privmsg', u'nickserv', u'identify {}'.format(passwd))
		c.join(self.config.get(u'irc:channel'))

	def _answers_8ball(self):
		return [
			u'As I see it, yes.',
			u'Ask again later.',
			u'Better not tell you now.',
			u'Cannot predict now.',
			u'Concentrate and ask again.',
			u'Don\'t count on it.',
			u'It is certain.',
			u'It is decidedly so.',
			u'Most likely.',
			u'My reply is no.',
			u'My sources say no.',
			u'Outlook good.',
			u'Outlook not so good.',
			u'Reply hazy, try again.',
			u'Signs point to yes.',
			u'Very doubtful.',
			u'Without a doubt.',
			u'Yes.',
			u'Yes - definitely.',
			u'You may rely on it.'
		]

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

		self.log.info(u'Looking for URLs in: {}'.format(text))

		urls = []
		for token in text.split():
			o = urlparse(token)
			if u'http' in o.scheme and o.netloc:
				url = o.geturl()
				self.log.info(u'Found a URL: {}'.format(url))
				urls.append(url)
		return urls

	def _get_api_auth_for_nick(self, nick):
		'''Try to get the user_id and api key for a nick.
		Return a dict with keys 'user_id' and 'key', keys
		will be missing if they are not available.'''

		auth = {}

		stored_id = self.config.get_id_for_nick(nick)
		if stored_id:
			auth[u'user_id'] = int(stored_id)
		else:
			if self.rwdb is not None:
				db_id = self.rwdb.get_id_for_nick(nick)
				if db_id:
					auth[u'user_id'] = int(db_id)

		stored_key = self.config.get_key_for_nick(nick)
		if stored_key:
			auth[u'key'] = stored_key

		return auth

	def _get_current_channel_for_nick(self, nick):
		'''Try to find the channel that `nick` is currently tuned in to. Return
		a numeric channel id or None.'''

		# We can only do this if the database is available
		if self.rwdb is None:
			return None

		# Is there a stored user_id for this nick?
		stored_id = self.config.get_id_for_nick(nick)
		if stored_id:
			return self.rwdb.get_current_channel(stored_id)

		# Is this nick in the Rainwave database?
		db_id = self.rwdb.get_id_for_nick(nick)
		if db_id:
			return self.rwdb.get_current_channel(db_id)

		return None

	def _get_song_info_string(self, song_id):
		'''Get song info as single string'''

		info = self.rwdb.get_song_info(song_id)
		info[u'chan'] = self.rw.channel_id_to_name(info[u'chan_id'])
		m = u'{chan} // {album} [{album_id}] // {title} [{id}]'.format(**info)
		if not info[u'available']:
			seconds = info[u'release_time'] - int(time.time())
			m += u' (available in {})'.format(self._get_readable_time_span(seconds))
		return m

	def _get_readable_time_span(self, seconds):
		'''Convert seconds into readable time span'''
		m = u''
		if seconds < 60:
			m += u'{} seconds.'.format(seconds)
		else:
			minutes, seconds = divmod(seconds, 60)
			if minutes < 60:
				m += u'{:0>2d}:{:0>2d}.'.format(minutes, seconds)
			else:
				hours, minutes = divmod(minutes, 60)
				m += u'{:0>2d}:{:0>2d}:{:0>2d}'.format(hours, minutes, seconds)
		return m

	def _is_admin(self, nick):
		'''Check whether a nick has privileges to use administrative commands'''

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

	@property
	def missing_key(self):
		m = u'I do not have a key stored for you. Visit http://rainwave.cc/auth/ '
		m += u'to get a key and tell me about it with \x02!key add <key>\x02.'
		return m

	@property
	def missing_user_id(self):
		m = u'I do not have a user id stored for you. Visit '
		m += u'http://rainwave.cc/auth/ to look up your user id and tell me about '
		m += u'it with \x02!id add <id>\x02.'
		return m

	def _periodic(self, c):
		# If I have not checked for forum activity for 'timeout:forumcheck'
		# seconds, check now

		self.log.info(u'Performing periodic tasks')

		nick = self.config.get(u'irc:nick')
		chan = self.config.get(u'irc:channel')
		output = Output(u'public')

		ltfc = int(self.config.get(u'lasttime:forumcheck', 0))
		tofc = int(self.config.get(u'timeout:forumcheck', 3600))
		if int(time.time()) > ltfc + tofc:
			self.log.info(u'Forum check timeout exceeded')
			self.handle_forum(nick, chan, output, force=False)

		ltmc = int(self.config.get(u'lasttime:musiccheck', 0))
		tomc = int(self.config.get(u'timeout:musiccheck', 3600))
		if int(time.time()) > ltmc + tomc:
			self.log.info(u'Music check timeout exceeded')
			for rchan in self.channel_ids.keys():
				self.handle_newmusic(nick, chan, output, rchan=rchan, force=False)

		ltm = int(self.config.get(u'lasttime:msg', 0))
		toc = int(self.config.get(u'timeout:chat', 3600))
		if int(time.time()) > ltm + toc:
			self.log.info(u'Chat timeout exceeded, keep the conversation moving')
			talkrs = self._talk()
			for talkr in talkrs:
				self.config.set(u'msg:last', talkr)
				self.config.set(u'lasttime:msg', time.time())
				self.config.set(u'lasttime:respond', time.time())
				output.rs.append(talkr)

		for r in output.rs:
			self._to_irc(c, u'privmsg', chan, r)

	def _post_to_forum(self, forum_id, topic_id, m):
		'''Post a message to the phpBB forum

		Arguments:
			forum_id: phpBB forum id where the message should be sent
			topic_id: phpBB topic id where the message should be sent (cannot create
				new topics)
			m: message to be sent'''

		url = self.config.get(u'funnytopic:url')
		if url is None:
			self.log.warning(u'Please !set funnytopic:url')
			return

		u = self.config.get(u'funnytopic:username')
		if u is None:
			self.log.warning(u'Please !set funnytopic:username')
			return

		p = self.config.get(u'funnytopic:password')
		if p is None:
			self.log.warning(u'Please !set funnytopic:password')
			return

		m = m.replace(u'<', u'&lt;').replace(u'>', u'&gt;')

		post_data = {u'u': u, u'p': p, u'f': forum_id, u't': topic_id, u'm': m}
		requests.post(url, data=post_data)

	def _shorten(self, lurl):
		'''Shorten a URL

		Arguments:
			lurl: The long url

		Returns: a string, the short url'''

		payload = json.dumps({u'longUrl': lurl})
		headers = {u'content-type': u'application/json'}

		gkey = self.config.get(u'googleapikey')
		url = u'https://www.googleapis.com/urlshortener/v1/url?key={}'.format(gkey)
		d = requests.post(url, data=payload, headers=headers)
		result = d.json()

		if u'id' in result:
			return result[u'id']

		return u''

	def _talk(self, msg=None):
		'''Engage the brain, respond when appropriate

		Arguments:
			msg: the message to learn and possible reply to

		Returns: a list of strings'''

		# If I am not replying to anything in particular, use the last message
		if msg is None:
			msg = self.config.get(u'msg:last')
		if msg is None:
			return []

		# Ignore messages with certain words
		if self.reignore:
			result = self.reignore.search(msg)
			if result is not None:
				return []

		# Clean up the message before sending to the brain
		tobrain = msg
		tobrain = tobrain.replace(self.config.get(u'irc:nick'), u'')
		tobrain = tobrain.replace(u':', u'')

		self.brain.learn(tobrain)

		return [self.brain.reply(tobrain)]

	def _to_irc(self, c, msgtype, target, msg):
		'''Send an IRC message'''

		self.log.debug(u'Sending {} to {} -- {}'.format(msgtype, target, msg))

		if hasattr(c, msgtype):
			f = getattr(c, msgtype)
			if type(msg) is not unicode:
				msg = unicode(msg, u'utf-8')
			try:
				f(target, msg)
			except:
				self.log.exception(u'Problem sending to IRC')
		else:
			self.log.error(u'Invalid message type \'{}\''.format(msgtype))


def main():
	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0)
	except (OSError, AttributeError):
		# Non-Unix systems will run wormgas in the foreground.
		pass

	if len(sys.argv) > 1:
		sleeptime = float(sys.argv[1])
	else:
		sleeptime = 0
	time.sleep(sleeptime)

	bot = wormgas()
	bot.start()

if __name__ == u'__main__':
	main()
