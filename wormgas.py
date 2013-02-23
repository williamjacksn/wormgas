#!/usr/bin/env python
"""
wormgas -- IRC bot for Rainwave (http://rainwave.cc)
https://github.com/subtlecoolness/wormgas
"""

import httplib
import json
import lxml.html
import logging, logging.handlers
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib, urllib2
from urlparse import urlparse

import dbaccess
import rainwave
from ircbot import SingleServerIRCBot
from cobe.brain import Brain
from CollectionOfNamedLists import CollectionOfNamedLists

_abspath = os.path.abspath(__file__)
_commands = set()

PRIVMSG = "__privmsg__"

class Output(object):
	"""Dead-simple abstraction for splitting output between public and private.

	When created, specify the default output, either public or private. This
	way command handlers don't have to care about the output mode unless they
	need to.
	"""
	def __init__(self, default):
		"""Create an Output object.

		Args:
			default: string, either "public" or "private".
		"""
		self.rs = []
		self.privrs = []
		if default == "public":
			self._default = self.rs
		elif default == "private":
			self._default = self.privrs
		else:
			raise ValueError("default should be 'public' or 'private'")

	@property
	def default(self):
		"""The default output list."""
		return self._default

def command_handler(command):
	"""Decorate a method to register as a command handler for provided regex."""
	def decorator(func):
		# Compile the command into a regex.
		regex = re.compile(command, re.I)

		def wrapped(self, nick, msg, channel, output):
			"""Command with stored regex that will execute if it matches msg."""
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

	answers_8ball = [
		"As I see it, yes.",
		"Ask again later.",
		"Better not tell you now.",
		"Cannot predict now.",
		"Concentrate and ask again.",
		"Don't count on it.",
		"It is certain.",
		"It is decidedly so.",
		"Most likely.",
		"My reply is no.",
		"My sources say no.",
		"Outlook good.",
		"Outlook not so good.",
		"Reply hazy, try again.",
		"Signs point to yes.",
		"Very doubtful.",
		"Without a doubt.",
		"Yes.",
		"Yes - definitely.",
		"You may rely on it."
	]

	channel_names = (
		"Rainwave Network",
		"Game channel",
		"OCR channel",
		"Covers channel",
		"Chiptune channel",
		"All channel"
	)

	channel_codes = (
		None,
		"game",
		"ocr",
		"cover",
		"chip",
		"all"
	)

	channel_ids = {
		"rw":     1,
		"game":   1,
		"oc":     2,
		"ocr":    2,
		"vw":     3,
		"mw":     3,
		"cover":  3,
		"covers": 3,
		"bw":     4,
		"chip":   4,
		"ch":     4,
		"ow":     5,
		"omni":   5,
		"all":    5
	}

	def __init__(self, config_db="config.sqlite", log_file="wormgas.log"):
		self.path, self.file = os.path.split(_abspath)
		self.brain = Brain(self.path + "/brain.sqlite")
		self.config = dbaccess.Config("%s/%s" % (self.path, config_db))
		self.ph = CollectionOfNamedLists("%s/ph.json" % self.path)
		self.rw = rainwave.RainwaveClient()

		# Set up logging.
		self.log = logging.getLogger("wormgas")
		self.log_handler = None
		if log_file:
			self.log.setLevel(logging.DEBUG)
			logpath = "%s/%s" % (self.path, log_file)
			self.log_handler = logging.handlers.RotatingFileHandler(
				logpath, maxBytes=20000000, backupCount=1)
			self.log_handler.setFormatter(logging.Formatter(
				"%(asctime)s - %(levelname)s - %(message)s"))
			logging.getLogger().addHandler(self.log_handler)

		# Set up Rainwave DB access if available.
		try:
			self.rwdb = dbaccess.RainwaveDatabase(self.config)
			self.rwdb.connect()
		except dbaccess.RainwaveDatabaseUnavailableError:
			self.rwdb = None

		args = sys.argv[1:]
		for arg in args:
			if arg.startswith("--set-"):
				key,value = arg[6:].split("=", 1)
				print "Setting '%s' to '%s'." % (key, value)
				self.config.set(key, value)

		# Set up ignore if the ignore list is non-empty.
		ignore = self.config.get("msg:ignore", "")
		self.reignore = None
		if ignore:
			self.reignore = re.compile(ignore)

		server = self.config.get("irc:server")
		nick = self.config.get("irc:nick")
		name = self.config.get("irc:name")
		SingleServerIRCBot.__init__(self, [(server, 6667)], nick, name)

	def stop(self):
		"""Save all data and shut down the bot."""
		del self.config
		del self.brain
		if self.log_handler:
			logging.getLogger().removeHandler(self.log_handler)

	_events_not_logged = [
		"all_raw_messages",
		"created",
		"endofmotd",
		"featurelist",
		"luserchannels",
		"luserclient",
		"luserme",
		"luserop",
		"luserunknown",
		"motd",
		"motdstart",
		"myinfo",
		"n_global",
		"n_local"
	]

	def _dispatcher(self, c, e):
		et = e.eventtype()
		if et not in self._events_not_logged:
			s = e.source()
			t = e.target()
			self.log.debug("%s, %s, %s -- %s" % (et, s, t, e.arguments()))
		SingleServerIRCBot._dispatcher(self, c, e)

	@command_handler("!8ball")
	def handle_8ball(self, nick, channel, output):
		"""Ask a question of the magic 8ball."""

		self.log.info("%s used !8ball" % nick)

		result = random.choice(self.answers_8ball)
		# Private messages always get the result.
		if channel == PRIVMSG:
			output.default.append(result)
			return

		# Otherwise, check for the cooldown and respond accordingly.
		ltb = int(self.config.get("lasttime:8ball", 0))
		wb = int(self.config.get("wait:8ball", 0))
		if ltb < time.time() - wb:
			output.default.append(result)
			if "again" not in result:
				self.config.set("lasttime:8ball", time.time())
		else:
			output.privrs.append(result)
			wait = ltb + wb - int(time.time())
			r = "I am cooling down. You cannot use !8ball in "
			r += "%s for another %s seconds." % (channel, wait)
			output.privrs.append(r)

	@command_handler(r"^!c(ool)?d(own)? add(\s(?P<unit>\w+))?"
		r"(\s(?P<unit_id>\d+))?(\s(?P<cdg_name>.+))?")
	def handle_cooldown_add(self, nick, channel, output, unit=None,
		unit_id=None, cdg_name=None):
		"""Add a song or album to a cooldown group."""

		self.log.info("%s used !cooldown add" % nick)
		self.log.info("unit: %s, unit_id: %s, cdg_name: %s" % (unit, unit_id,
			cdg_name))

		# This command requires administrative privileges
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !cooldown add" % nick)
			return

		# This command requires the Rainwave database
		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		# cdg_name must be specified
		if cdg_name is None:
			self.handle_help(nick, channel, output, topic="cooldown")
			return

		# unit_id should be numeric
		if unit_id is None:
			self.handle_help(nick, channel, output, topic="cooldown")
			return

		if unit_id.isdigit():
			unit_id = int(unit_id)
		else:
			self.handle_help(nick, channel, output, topic="cooldown")
			return

		# unit should be "song" or "album"

		if unit == "song":
			rcode, rval = self.rwdb.add_song_to_cdg(unit_id, cdg_name)
			if rcode == 0:
				rchan = self.channel_names[rval[0]]
				rval = (rchan,) + rval[1:]
				r = "Added %s / %s / %s to cooldown group %s" % rval
				output.privrs.append(r)
			else:
				output.privrs.append(rval)
		elif unit == "album":
			rcode, rval = self.rwdb.add_album_to_cdg(unit_id, cdg_name)
			if rcode == 0:
				rchan = self.channel_names[rval[0]]
				rval = (rchan,) + rval[1:]
				r = "Added %s / %s to cooldown group %s" % rval
				output.privrs.append(r)
			else:
				output.privrs.append(rval)
		else:
			self.handle_help(nick, channel, output, topic="cooldown")

	@command_handler(r"^!c(ool)?d(own)? drop(\s(?P<unit>\w+))?"
		r"(\s(?P<unit_id>\d+))?(\s(?P<cdg_name>.+))?")
	def handle_cooldown_drop(self, nick, channel, output, unit=None,
		unit_id=None, cdg_name=None):
		"""Remove a song or album from a cooldown group"""

		self.log.info("%s used !cooldown drop" % nick)
		self.log.info("unit: %s, unit_id: %s, cdg_name: %s" % (unit, unit_id,
			cdg_name))

		# This command requires administrative privileges

		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !cooldown add" % nick)
			return

		# This command requires the Rainwave database

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		# unit_id should be numeric

		if unit_id is None:
			self.handle_help(nick, channel, output, topic="cooldown")
			return

		if unit_id.isdigit():
			unit_id = int(unit_id)
		else:
			self.handle_help(nick, channel, output, topic="cooldown")
			return

		# unit should be "song" or "album"

		if unit == "song":
			if cdg_name is None:
				rcode, rval = self.rwcd.drop_song_from_all_cdgs(unit_id)
				if rcode == 0:
					rchan = self.channel_names[rval[0]]
					rval = (rchan,) + rval[1:]
					r = "Dropped %s / %s / %s from all cooldown groups" % rval
					output.privrs.append(r)
				else:
					output.privrs.append(rval)
			else:
				rcode, rval = self.rwdb.drop_song_from_cdg_by_name(unit_id, cdg_name)
				if rcode == 0:
					rchan = self.channel_names[rval[0]]
					rval = (rchan,) + rval[1:]
					r = "Dropped %s / %s / %s from cooldown group %s" % rval
					output.privrs.append(r)
				else:
					output.privrs.append(rval)
		elif unit == "album":
			if cdg_name is None:
				rcode, rval = self.rwdb.drop_album_from_all_cdgs(unit_id)
				if rcode == 0:
					rchan = self.channel_names[rval[0]]
					rval = (rchan,) + rval[1:]
					r = "Dropped %s / %s from all cooldown groups" % rval
					output.privrs.append(r)
				else:
					output.privrs.append(rval)
			else:
				rcode, rval = self.rwdb.drop_album_from_cdg_by_name(unit_id, cdg_name)
				if rcode == 0:
					rchan = self.channel_names[rval[0]]
					rval = (rchan,) + rval[1:]
					r = "Dropped %s / %s from cooldown group %s" % rval
					output.privrs.append(r)
				else:
					output.privrs.append(rval)
		else:
			self.handle_help(nick, channel, output, topic="cooldown")

	@command_handler(r"!election(\s(?P<rchan>\w+))?(\s(?P<index>\d))?")
	@command_handler(r"!el(?P<rchan>\w+)?(\s(?P<index>\d))?")
	def handle_election(self, nick, channel, output, rchan=None, index=None):
		"""Show the candidates in an election"""

		self.log.info("%s used !election" % nick)

		# Make sure the index is valid.
		try:
			index = int(index)
		except TypeError:
			index = 0
		if index not in [0, 1]:
			# Not a valid index, return the help text.
			self.handle_help(nick, channel, output, topic="election")
			return

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append("I cannot determine the channel")
				self.handle_help(nick, channel, output, topic="election")
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic="election")
			return

		sched_config = "el:%s:%s" % (cid, index)
		sched_id, text = self._fetch_election(index, cid)

		if sched_id == 0:
			# Something strange happened while fetching the election
			output.default.append(text)
			return

		# Prepend the message description to the output string.
		time = ["Current", "Future"][index]
		rchn = self.channel_names[cid] # radio channel name
		result = "%s election on the %s: %s" % (time, rchn, text)

		if channel == PRIVMSG:
			output.privrs.append(result)
		elif sched_id == self.config.get(sched_config):
			# !election has already been called for this election
			output.privrs.append(result)
			r = "I am cooling down. You can only use !election in "
			r += "%s once per election." % channel
			output.privrs.append(r)
		else:
			output.default.append(result)
			self.config.set(sched_config, sched_id)

	def _fetch_election(self, index, cid):
		"""Return (sched_id, election string) for given index and cid.

		A sched_id is a unique ID given to every scheduled event, including
		elections. The results of this call can therefore be cached locally
		using the sched_id as the cache key.
		"""

		text = ""

		data = self.rw.get_timeline(cid)
		try:
			elec = data["sched_next"][index]
		except IndexError:
			# There is no future election?
			return 0, "There is no election at the specified index."

		for i, song in enumerate(elec["song_data"], start=1):
			album = song["album_name"]
			title = song["song_title"]
			artt = ", ".join(art["artist_name"] for art in song["artists"])
			text += " \x02[%s]\x02 %s / %s by %s" % (i, album, title, artt)
			etype = song["elec_isrequest"]
			if etype in (3, 4):
				requestor = song["song_requestor"]
				text += " (requested by %s)" % requestor
			elif etype in (0, 1):
				text += " (conflict)"
		return elec["sched_id"], text

	@command_handler("!flip")
	def handle_flip(self, nick, channel, output):
		"""Simulate a coin flip"""

		self.log.info("%s used !flip" % nick)

		answers = ("Heads!", "Tails!")
		result = random.choice(answers)
		if channel == PRIVMSG:
			output.default.append(result)
			return

		ltf = int(self.config.get("lasttime:flip", 0))
		wf = int(self.config.get("wait:flip", 0))
		if ltf < time.time() - wf:
			output.default.append(result)
			self.config.set("lasttime:flip", time.time())
		else:
			output.privrs.append(result)
			wait = ltf + wf - int(time.time())
			r = "I am cooling down. You cannot use !flip in %s " % channel
			r += "for another %s seconds." % wait
			output.privrs.append(r)

	@command_handler(r"!forum")
	def handle_forum(self, nick, channel, output, force=True):
		"""Check for new forum posts, excluding forums where the anonymous user
		has no access"""

		self.log.info("Looking for new forum posts, force is %s" % force)

		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !forum" % nick)
			return

		self.config.set("lasttime:forumcheck", time.time())

		if force:
			self.config.unset("maxid:forum")

		maxid = self.config.get("maxid:forum", 0)
		self.log.info("Looking for forum posts newer than %s" % maxid)

		if self.rwdb:
			newmaxid = self.rwdb.get_max_forum_post_id()
		else:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		if newmaxid > int(self.config.get("maxid:forum", 0)):
			r, url = self.rwdb.get_forum_post_info()
			surl = self._shorten(url)
			output.rs.append("New on the forums! %s <%s>" % (r, surl))
			self.config.set("maxid:forum", newmaxid)

	@command_handler(r"^!help(\s(?P<topic>\w+))?")
	def handle_help(self, nick, channel, output, topic=None):
		"""Look up help about a topic"""

		self.log.info("%s used !help" % nick)

		is_admin = self._is_admin(nick)
		rs = []

		channelcodes = ("Channel codes are \x02" +
			"\x02, \x02".join(self.channel_ids.keys()) + "\x02")
		notpermitted = "You are not permitted to use this command"
		wiki = ("More help is available at "
			"https://github.com/subtlecoolness/wormgas/wiki")

		if topic in ["all", None]:
			rs.append("Use \x02!help [<topic>]\x02 with one of these topics: "
				"8ball, election, flip, history, id, key, lookup, lstats, "
				"nowplaying, prevplayed, rate, request, roll, rps, stats, "
				"unrated, ustats, vote")
			if is_admin:
				rs.append("Administration topics: cooldown, forum, newmusic, otp, ph, "
					"refresh, restart, set, stop, unset")
			rs.append(wiki)
		elif topic == "8ball":
			rs.append("Use \x02!8ball\x02 to ask a question of the magic 8ball")
		elif topic in ["cooldown", "cd"]:
			if is_admin:
				rs.append("Use \x02!cooldown add song|album <song_id|album_id> "
					"<cdg_name>\x02 to add a song or album to a cooldown group")
				rs.append("Use \x02!cooldown drop song|album "
					"<song_id|album_id> [<cdg_name>]\x02 to remove a song or "
					"album from a cooldown group, leave off <cdg_name> to "
					"remove a song or album from all cooldown groups")
				rs.append("Short version is \x02!cd ...\x02")
			else:
				rs.append(notpermitted)
		elif topic in ["election", "el"]:
			rs.append("Use \x02!election <channel> [<index>]\x02 to see the "
				"candidates in an election")
			rs.append("Short version is \x02!el<channel> [<index>]\x02")
			rs.append("Index should be 0 (current) or 1 (future), default is 0")
			rs.append(channelcodes)
		elif topic == "flip":
			rs.append("Use \x02!flip\x02 to flip a coin")
		elif topic == "forum":
			if is_admin:
				rs.append("Use \x02!forum\x02 to announce the most recent "
					"forum post in the channel")
			else:
				rs.append(notpermitted)
		elif topic in ["history", "hs"]:
			rs.append("Use \x02!history <channel>\x02 to see the last several "
				"songs that played on a channel")
			rs.append("Short version is \x02!hs<channel>\x02")
			rs.append(channelcodes)
		elif topic == "id":
			rs.append("Look up your Rainwave user id at "
				"http://rainwave.cc/auth/ and use \x02!id add <id>\x02 to tell "
				"me about it")
			rs.append("Use \x02!id drop\x02 to delete your user id and \x02!id "
				"show\x02 to see it")
		elif topic == "key":
			rs.append("Get an API key from http://rainwave.cc/auth/ and use "
				"\x02!key add <key>\x02 to tell me about it")
			rs.append("Use \x02!key drop\x02 to delete your key and \x02!key "
				"show\x02 to see it")
		elif topic in ["lookup", "lu"]:
			rs.append("Use \x02!lookup <channel> song|album <text>\x02 "
				"to search for songs or albums with <text> in the title")
			rs.append("Short version is \x02!lu<channel> song|album "
				"<text>\x02")
			rs.append(channelcodes)
		elif topic == "lstats":
			rs.append("Use \x02!lstats [<channel>]\x02 to see information "
				"about current listeners, all channels are aggregated if you "
				"leave off <channel>")
			rs.append("Use \x02!lstats chart [<num>]\x02 to see a chart of "
				"average hourly listener activity over the last <num> days, "
				"leave off <num> to use the default of 30")
			rs.append(channelcodes)
		elif topic == "newmusic":
			if is_admin:
				rs.append("Use \x02!newmusic <channel>\x02 to announce the "
					"three most recently added songs on the channel")
				rs.append(channelcodes)
			else:
				rs.append(notpermitted)
		elif topic in ["nowplaying", "np"]:
			rs.append("Use \x02!nowplaying <channel>\x02 to show what is "
				"now playing on the radio")
			rs.append("Short version is \x02!np<channel>\x02")
			rs.append(channelcodes)
		elif topic == "otp":
			if is_admin:
				rs.append("Use \x02!otp\x02 to see all One-Time Plays currently "
					"scheduled on all channels")
			else:
				rs.append(notpermitted)
		elif topic == "ph":
			if is_admin:
				rs.append("Use \x02!ph <command>\x02 to manage your Power Hour "
					"planning list")
				rs.append("Refer to https://github.com/subtlecoolness/wormgas/wiki/ph "
					"for details")
			else:
				rs.append(notpermitted)
		elif topic in ["prevplayed", "pp"]:
			rs.append("Use \x02!prevplayed <channel> [<index>]\x02 to show "
				"what was previously playing on the radio")
			rs.append("Short version is \x02!pp<channel> [<index>]\x02")
			rs.append("Index should be one of (0, 1, 2), 0 is default, higher "
				"numbers are further in the past")
			rs.append(channelcodes)
		elif topic in ["rate", "rt"]:
			rs.append("Use \x02!rate <channel> <rating>\x02 to rate the "
				"currently playing song")
			rs.append("Short version is \x02!rt<channel> <rating>\x02")
			rs.append(channelcodes)
		elif topic == "refresh":
			if is_admin:
				rs.append("Use \x02!refresh\x02 to show pending or running "
					"playlist refresh jobs")
				rs.append("Use \x02!refresh <channel>\x02 to request a "
					"playlist refresh for a particular channel")
				rs.append(channelcodes)
			else:
				rs.append(notpermitted)
		elif topic in ["request", "rq"]:
			rs.append("Use \x02!request <channel> <song_id>\x02 to add a "
				"song to your request queue, find the <song_id> using "
				"\x02!lookup\x02 or \x02!unrated\x02")
			rs.append("Short version is \x02!rq<channel> <song_id>\x02")
			rs.append(channelcodes)
		elif topic == "restart":
			if is_admin:
				rs.append("Use \x02!restart\x02 to restart the bot")
			else:
				rs.append(notpermitted)
		elif topic == "roll":
			rs.append("Use \x02!roll [#d^]\x02 to roll a ^-sided die # times")
		elif topic == "rps":
			rs.append("Use \x02!rock\x02, \x02!paper\x02, or \x02!scissors\x02 "
				"to play a game")
			rs.append("Use \x02!rps record [<nick>]\x02 to see the record for "
				"<nick>, leave off <nick> to see your own record, use nick "
				"'!global' to see the global record")
			rs.append("Use \x02!rps stats [<nick>]\x02 to see some statistics "
				"for <nick>, leave off <nick> to see your own statistics")
			rs.append("Use \x02!rps reset\x02 to reset your record and delete "
				"your game history, there is no confirmation and this cannot "
				"be undone")
			rs.append("Use \x02!rps who\x02 to see a list of known players")
			if is_admin:
				rs.append("Administrators can use \x02!rps rename <oldnick> "
					"<newnick>\x02 to reassign stats and game history from one "
					"nick to another")
		elif topic == "set":
			if is_admin:
				rs.append("Use \x02!set [<id>] [<value>]\x02 to display or "
					"change configuration settings")
				rs.append("Leave off <value> to see the current setting")
				rs.append("Leave off <id> and <value> to see a list of all "
					"available config ids")
			else:
				rs.append(notpermitted)
		elif topic == "stats":
			rs.append("Use \x02!stats [<channel>]\x02 to show information "
				"about the music collection, leave off <channel> to see the "
				"aggregate for all channels")
			rs.append(channelcodes)
		elif topic == "stop":
			if is_admin:
				rs.append("Use \x02!stop\x02 to shut down the bot")
			else:
				rs.append(notpermitted)
		elif topic == "unrated":
			rs.append("Use \x02!unrated <channel> [<num>]\x02 to see songs "
				"you have not rated, <num> can go up to 12, leave it off to "
				"see just one song")
			rs.append(channelcodes)
		elif topic == "unset":
			if is_admin:
				rs.append("Use \x02!unset <id>\x02 to remove a configuration "
					"setting")
			else:
				rs.append(notpermitted)
		elif topic == "ustats":
			rs.append("Use \x02!ustats [<nick>]\x02 to show user statistics "
				"for <nick>, leave off <nick> to see your own statistics")
		elif topic in ["vote", "vt"]:
			rs.append("Use \x02!vote <channel> <index>\x02 to vote in the "
				"current election, find the <index> with \x02!election\x02")
			rs.append(channelcodes)
		else:
			rs.append("I cannot help you with '%s'" % topic)
			rs.append(wiki)

		output.privrs.extend(rs)

	@command_handler(r"!history(\s(?P<rchan>\w+))?")
	@command_handler(r"!hs(?P<rchan>\w+)?")
	def handle_history(self, nick, channel, output, rchan=None):
		"""Show the last several songs that played on the radio"""

		self.log.info("%s used !history" % nick)

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append("I cannot determine the channel")
				self.handle_help(nick, channel, output, topic="history")
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic="history")
			return
		rchn = self.channel_names[cid]

		for song in self.rwdb.get_history(cid):
			r = "%s: %s -- %s [%s] / %s [%s]" % ((rchn,) + song)
			output.privrs.append(r)

		output.privrs.reverse()

	@command_handler(r"^!id(\s(?P<mode>\w+))?(\s(?P<id>\d+))?")
	def handle_id(self, nick, channel, output, mode=None, id=None):
		"""Manage correlation between an IRC nick and Rainwave User ID

		Arguments:
			mode: string, one of "help", "add", "drop", "show"
			id: numeric, the person's Rainwave User ID"""

		self.log.info("%s used !id" % nick)

		# Make sure this nick is in the user_keys table
		self.config.store_nick(nick)

		if mode == "add" and id:
			self.config.add_id_to_nick(id, nick)
			r = "I assigned the user id %s to nick '%s'" % (id, nick)
			output.privrs.append(r)
		elif mode == "drop":
			self.config.drop_id_for_nick(nick)
			output.privrs.append("I dropped the user id for nick '%s'" % nick)
		elif mode == "show":
			stored_id = self.config.get_id_for_nick(nick)
			if stored_id:
				r = "The user id for nick '%s' is %s" % (nick, stored_id)
				output.privrs.append(r)
			else:
				r = "I do not have a user id for nick '%s'" % nick
				output.privrs.append(r)
		else:
			self.handle_help(nick, channel, output, topic="id")

	@command_handler(r"^!key(\s(?P<mode>\w+))?(\s(?P<key>\w{10}))?")
	def handle_key(self, nick, channel, output, mode=None, key=None):
		"""Manage API keys

		Arguments:
			mode: string, one of "help", "add", "drop", "show"
			key: string, the API key to add"""

		self.log.info("%s used !key" % nick)

		# Make sure this nick is in the user_keys table
		self.config.store_nick(nick)

		if mode == "add" and key:
			self.config.add_key_to_nick(key, nick)
			r = "I assigned the API key '%s' to nick '%s'" % (key, nick)
			output.privrs.append(r)
		elif mode == "drop":
			self.config.drop_key_for_nick(nick)
			output.privrs.append("I dropped the API key for nick '%s'" % nick)
		elif mode == "show":
			stored_id = self.config.get_key_for_nick(nick)
			if stored_id:
				r = "The API key for nick '%s' is '%s'" % (nick, stored_id)
				output.privrs.append(r)
			else:
				r = "I do not have an API key for nick '%s'" % nick
				output.privrs.append(r)
		else:
			self.handle_help(nick, channel, output, topic="key")

	@command_handler(r"^!lookup(\s(?P<rchan>\w+))?(\s(?P<mode>\w+))?"
		r"(\s(?P<text>.+))?")
	@command_handler(r"^!lu(?P<rchan>\w+)?(\s(?P<mode>\w+))?"
		r"(\s(?P<text>.+))?")
	def handle_lookup(self, nick, channel, output, rchan, mode, text):
		"""Look up (search for) a song or album"""

		self.log.info("%s used !lookup" % nick)

		if not self.rwdb:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		if rchan in ("song", "album"):
			text = mode + " " + str(text)
			mode = rchan
			rchan = None

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append("I cannot determine the channel")
				self.handle_help(nick, channel, output, topic="lookup")
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic="lookup")
			return
		rchn = self.channel_names[cid]

		if mode == "song":
			rows, unreported_results = self.rwdb.search_songs(cid, text)
			out = "%(rchan)s: %(album_name)s / %(song_title)s [%(song_id)s]"
		elif mode == "album":
			rows, unreported_results = self.rwdb.search_albums(cid, text)
			out = "%(rchan)s: %(album_name)s [%(album_id)s]"
		else:
			self.handle_help(nick, channel, output, topic="lookup")
			return

		# If I got results, output them
		for row in rows:
			row["rchan"] = rchn
			output.privrs.append(out % row)

		# If I had to trim the results, be honest about it
		if unreported_results > 0:
			r = "%s: %s more result" % (rchn, unreported_results)
			if unreported_results > 1:
				r += "s"
			r += (". If you do not see what you are looking for, be more "
				"specific with your search.")
			output.privrs.append(r)

			# If I did not find anything with this search, mention that
			if len(output.privrs) < 1:
				r = "%s: No results." % rchn
				output.privrs.append(r)
			elif unreported_results < 1:
				# I got between 1 and 10 results
				num = len(output.privrs)
				r = "%s: Your search returned %s result" % (rchn, num)
				if num > 1:
					r += "s"
				r += "."
				output.privrs.insert(0, r)

	@command_handler(r"^!lstats(\s(?P<rchan>\w+))?(\s(?P<days>\d+))?")
	def handle_lstats(self, nick, channel, output, rchan=None, days=30):
		""" Reports listener statistics, as numbers or a chart

		Arguments:
			rchan: channel to ask about, or maybe "chart"
			days: number of days to include data for chart"""

		self.log.info("%s used !lstats" % nick)

		if not self.rwdb:
			output.default.append("The Rainwave database is unavailable.")
			return

		rs = []

		if rchan:
			rchan = rchan.lower()

		cid = self.channel_ids.get(rchan, 0)
		rchn = self.channel_names[cid]

		try:
			days = int(days)
		except TypeError:
			days = 30

		if rchan != "chart":
			regd, guest = self.rwdb.get_listener_stats(cid)
			r = "%s: %s registered users, " % (rchn, regd)
			r += "%s guests." % guest
			rs.append(r)
		elif rchan == "chart":

			# Base url
			url = "http://chart.apis.google.com/chart"

			# Axis label styles
			url += "?chxs=0,676767,11.5,-1,l,676767"

			# Visible axes
			url += "&chxt=y,x"

			# Bar width and spacing
			url += "&chbh=a"

			# Chart size
			url += "&chs=600x400"

			# Chart type
			url += "&cht=bvs"

			# Series colors
			url += "&chco=A2C180,3D7930,3399CC,244B95,FFCC33,"
			url += "FF9900,cc80ff,66407f,900000,480000"

			# Chart legend text
			url += "&chdl=Game+Guests|Game+Registered|OCR+Guests|"
			url += "OCR+Registered|Covers+Guests|Covers+Registered|"
			url += "Chiptune+Guests|Chiptune+Registered|All+Guests|"
			url += "All+Registered"

			# Chart title
			url += "&chtt=Rainwave+Average+Hourly+Usage+by+User+Type+and+"
			url += "Channel|%s+Day" % days
			if days > 1:
				url += "s"
			url += "+Ending+"
			url += time.strftime("%Y-%m-%d", time.gmtime())

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
			url += "&chd=t:"
			url += ",".join(["%s" % el for el in game_g]) + "|"
			url += ",".join(["%s" % el for el in game_r]) + "|"
			url += ",".join(["%s" % el for el in ocr_g]) + "|"
			url += ",".join(["%s" % el for el in ocr_r]) + "|"
			url += ",".join(["%s" % el for el in cover_g]) + "|"
			url += ",".join(["%s" % el for el in cover_r]) + "|"
			url += ",".join(["%s" % el for el in chip_g]) + "|"
			url += ",".join(["%s" % el for el in chip_r]) + "|"
			url += ",".join(["%s" % el for el in all_g]) + "|"
			url += ",".join(["%s" % el for el in all_r])

			# Axis ranges
			url += "&chxr=0,0,%s|1,0,23" % lceil

			# Scale for text format with custom range
			url += "&chds="
			t1 = "0,%s" % lceil
			t2 = []
			for i in range(10):
				t2.append(t1)
			url += ",".join(t2)
			rs.append(self._shorten(url))
		else:
			self.handle_help(nick, channel, output, topic="lstats")
			return

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		ltls = int(self.config.get("lasttime:lstats", 0))
		wls = int(self.config.get("wait:lstats", 0))
		if ltls < time.time() - wls:
			output.default.extend(rs)
			self.config.set("lasttime:lstats", time.time())
		else:
			output.privrs.extend(rs)
			wait = ltls + wls - int(time.time())
			output.privrs.append("I am cooling down. You cannot use !lstats in "
				"%s for another %s seconds." % (channel, wait))

	@command_handler(r"!newmusic(\s(?P<rchan>\w+))?")
	def handle_newmusic(self, nick, channel, output, rchan=None, force=True):
		"""Check for new music and announce up to three new songs per station"""

		r = "Looking for new music on channel %s" % rchan
		r += ", force is %s" % force
		self.log.info(r)

		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !newmusic" % nick)
			return

		self.config.set("lasttime:musiccheck", time.time())

		if rchan:
			rchan = rchan.lower()

		if rchan in self.channel_ids:
			cid = self.channel_ids[rchan]
		else:
			self.handle_help(nick, channel, output, topic="newmusic")
			return

		rchn = self.channel_names[cid]
		self.log.info("Looking for new music on the %s" % rchn)

		if force:
			self.config.unset("maxid:%s" % cid)

		maxid = self.config.get("maxid:%s" % cid, 0)
		self.log.info("Looking for music newer than %s" % maxid)

		if self.rwdb:
			newmaxid = self.rwdb.get_max_song_id(cid)
		else:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		if newmaxid > int(maxid):
			songs = self.rwdb.get_new_song_info(cid)
			for r, url in songs:
				msg = "New on the %s: %s" % (rchn, r)
				if "http" in url:
					msg += " <%s>" % self._shorten(url)
				output.rs.append(msg)
			self.config.set("maxid:%s" % cid, newmaxid)

	@command_handler(r"!nowplaying(\s(?P<rchan>\w+))?")
	@command_handler(r"!np(?P<rchan>\w+)?")
	def handle_nowplaying(self, nick, channel, output, rchan=None):
		"""Report what is currently playing on the radio"""

		self.log.info("%s used !nowplaying" % nick)

		rs = []

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append("I cannot determine the channel")
				self.handle_help(nick, channel, output, topic="nowplaying")
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids[rchan]
		else:
			self.handle_help(nick, channel, output, topic="nowplaying")
			return
		rchn = self.channel_names[cid]

		data = self.rw.get_timeline(cid)
		sched_id = data["sched_current"]["sched_id"]
		sched_type = data["sched_current"]["sched_type"]
		if sched_type in (0, 4):
			np = data["sched_current"]["song_data"][0]
			album = np["album_name"]
			song = np["song_title"]
			arts = np["artists"]
			art_list = []
			for art in arts:
				art_name = art["artist_name"]
				art_list.append(art_name)
			artt = ", ".join(art_list)
			r = "Now playing on the %s: %s / %s by %s" % (rchn, album, song, artt)
			url = np["song_url"]
			if url and "http" in url:
				r += " <%s>" % self._shorten(url)

			if "elec_votes" in np:
				votes = np["elec_votes"]
			else:
				votes = 0
			ratings = np["song_rating_count"]
			avg = np["song_rating_avg"]

			r += " (%s vote" % votes
			if votes <> 1:
				r += "s"
			r += ", %s rating" % ratings
			if ratings <> 1:
				r += "s"
			r += ", rated %s" % avg

			type = np["elec_isrequest"]
			if type in (3, 4):
				r += ", requested by %s" % np["song_requestor"]
			elif type in (0, 1):
				r += ", conflict"
			r += ")"
			rs.append(r)
		else:
			r = "%s: I have no idea (sched_type = %s)" % (rchn, sched_type)
			rs.append(r)

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		if sched_id == int(self.config.get("np:%s" % cid, 0)):
			output.privrs.extend(rs)
			r = "I am cooling down. You can only use !nowplaying in "
			r += "%s once per song." % channel
			output.privrs.append(r)
		else:
			output.default.extend(rs)
			self.config.set("np:%s" % cid, sched_id)

	@command_handler(r"^!otp")
	def handle_otp(self, nick, channel, output):
		self.log.info("%s used !otp" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !otp" % nick)
			return

		for o in self.rwdb.get_all_otps():
			r = "%s [%s] %s / %s" % (self.channel_names[o[0]], o[1], o[2], o[3])
			output.default.append(r)

	@command_handler(r"^!ph (addalbum|aa) (?P<album_id>\d+)")
	def handle_ph_addalbum(self, nick, channel, output, album_id):
		"""Add all songs from an album to this user's Power Hour planning list"""

		self.log.info("%s used !ph addalbum" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if self.rwdb is None:
				output.privrs.append("The Rainwave database is unavailable")
				return

		album_id = int(album_id)
		for song_id in self.rwdb.get_album_songs(album_id):
			song_id = int(song_id)
			self.handle_ph_addsong(nick, channel, output, song_id)

	@command_handler(r"^!ph (addsong|add|as) (?P<song_id>\d+)")
	def handle_ph_addsong(self, nick, channel, output, song_id):
		"""Add a song to this user's Power Hour planning list"""

		self.log.info("%s used !ph addsong" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable")
			return

		song_id = int(song_id)
		m = self._get_song_info_string(song_id)

		if song_id in self.ph.items(nick):
			m += " is already in your Power Hour planning list"
		else:
			self.ph.add(nick, song_id)
			m += " added to your Power Hour planning list"

		output.privrs.append(m)

	@command_handler(r"^!ph (clear|cl)")
	def handle_ph_clear(self, nick, channel, output):
		"""Remove all songs from this user's Power Hour planning list"""

		self.log.info("%s used !ph clear" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		self.ph.clear(nick)
		output.privrs.append("Your Power Hour planning list has been cleared")

	@command_handler(r"^!ph (down|dn) (?P<song_id>\d+)")
	def handle_ph_down(self, nick, channel, output, song_id):
		"""Move a song down in this user's Power Hour planning list"""

		self.log.info("%s used !ph down" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		song_id = int(song_id)
		m = self._get_song_info_string(song_id)

		if song_id in self.ph.items(nick):
			self.ph.down(nick, song_id)
			m += " moved down in your Power Hour planning list"
		else:
			m += " is not in your Power Hour planning list"

		output.privrs.append(m)

	@command_handler(r"^!ph go (?P<rchan>\w+)")
	def handle_ph_go(self, nick, channel, output, rchan):
		"""Start a Power Hour on a channel using this user's Power Hour planning
		list"""

		self.log.info("%s used !ph go" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)

		if rchan in self.channel_ids:
			cid = self.channel_ids[rchan]
		else:
			output.privrs.append("%s is not a valid channel code" % rchan)
			return

		user_id = self.config.get_id_for_nick(nick)
		if user_id is None and self.rwdb:
			user_id = self.rwdb.get_id_for_nick(nick)
		if user_id is None:
			r = "I do not have a user id stored for you. Visit "
			r += "http://rainwave.cc/auth/ to look up your user id and tell me "
			r += "about it with \x02!id add <id>\x02"
			output.privrs.append(r)
			return

		# Get the key for this user
		key = self.config.get_key_for_nick(nick)
		if key is None:
			r = "I do not have a key stored for you. Visit "
			r += "http://rainwave.cc/auth/ to get a key and tell me about it "
			r += "with \x02!key add <key>\x02"
			output.privrs.append(r)
			return

		errors = 0
		for song_id in self.ph.items(nick):
			song_id = int(song_id)
			data = self.rw.add_one_time_play(cid, song_id, user_id, key)
			m = self._get_song_info_string(song_id) + u" // "
			if u"oneshot_add_result" in data:
				try:
					m += data[u"oneshot_add_result"][u"text"]
				except UnicodeDecodeError:
					self.log.exception(u"Not again. :(")
			else:
				try:
					m += data["error"]["text"]
				except UnicodeDecodeError:
					self.log.exception(u"Not again. :(")
				errors += 1
			output.privrs.append(m)

		if errors == 0:
			self.handle_ph_clear(nick, channel, output)

	@command_handler(r"!ph (length|len)")
	def handle_ph_length(self, nick, channel, output):
		"""Show number of songs and total running time of this user's Power Hour
		planning list"""

		self.log.info("%s used !ph length" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		count = len(self.ph.items(nick))
		seconds = 0
		for song_id in self.ph.items(nick):
			info = self.rwdb.get_song_info(song_id)
			seconds += info["length"]

		if count == 0:
			output.privrs.append("Your Power Hour planning list is empty")
			return

		m = "Your Power Hour planning list contains %s song" % count
		if count > 1:
			m += "s"

		m += " and will run for "
		if seconds < 60:
			m += "%s seconds" % seconds
		else:
			minutes, seconds = divmod(seconds, 60)
			if minutes < 60:
				m += "%02d:%02d" % (minutes, seconds)
			else:
				hours, minutes = divmod(minutes, 60)
				m += "%02d:%02d:%02d" % (hours, minutes, seconds)

		output.privrs.append(m)

	@command_handler(r"^!ph (list|ls)")
	def handle_ph_list(self, nick, channel, output):
		"""Show all songs in this user's Power Hour planning list"""

		self.log.info("%s used !ph list" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		count = 0
		for song_id in self.ph.items(nick):
			count += 1
			output.privrs.append(self._get_song_info_string(song_id))

		if count == 0:
			output.privrs.append("Your Power Hour planning list is empty")

	@command_handler(r"^!ph pause (?P<rchan>\w+)")
	def handle_ph_pause(self, nick, channel, output, rchan):
		"""Remove scheduled one-time plays from channel and put them in this user's
		Power Hour planning list"""

		self.log.info("%s used !ph pause" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if rchan in self.channel_ids:
			cid = self.channel_ids[rchan]
		else:
			output.privrs.append("%s is not a valid channel code" % rchan)
			return

		user_id = self.config.get_id_for_nick(nick)
		if user_id is None and self.rwdb:
			user_id = self.rwdb.get_id_for_nick(nick)
		if user_id is None:
			r = "I do not have a user id stored for you. Visit "
			r += "http://rainwave.cc/auth/ to look up your user id and tell me "
			r += "about it with \x02!id add <id>\x02"
			output.privrs.append(r)
			return

		# Get the key for this user
		key = self.config.get_key_for_nick(nick)
		if key is None:
			r = "I do not have a key stored for you. Visit "
			r += "http://rainwave.cc/auth/ to get a key and tell me about it "
			r += "with \x02!key add <key>\x02"
			output.privrs.append(r)
			return

		add_to_ph = []

		while True:
			data = self.rw.get_timeline(cid)
			otp_count = 0
			for event in data["sched_next"]:
				if event["sched_type"] == 4:
					otp_count += 1
					song_id = int(event["song_data"][0]["song_id"])
					if song_id in add_to_ph:
						continue
					m = self._get_song_info_string(song_id) + " // "
					add_to_ph.append(song_id)
					d = self.rw.delete_one_time_play(cid, event[u"sched_id"], user_id, key)
					if "oneshot_delete_result" in d:
						m += d["oneshot_delete_result"]["text"]
					else:
						m += d["error"]["text"]
					output.privrs.append(m)
			if otp_count == 0:
				break

		if len(add_to_ph) > 0:
			add_to_ph.extend(self.ph.items(nick))
			self.ph.set(nick, add_to_ph)
		else:
			output.privrs.append("No One-Time Plays scheduled on the %s" %
				self.channel_names[cid])

	@command_handler(r"^!ph (removealbum|ra) (?P<album_id>\d+)")
	def handle_ph_removealbum(self, nick, channel, output, album_id):
		"""Remove all songs in an album from this user's Power Hour planning list"""

		self.log.info("%s used !ph removealbum" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		album_id = int(album_id)
		for song_id in self.rwdb.get_album_songs(album_id):
			song_id = int(song_id)
			self.handle_ph_removesong(nick, channel, output, song_id)

	@command_handler(r"^!ph (remove|rm|removesong|rs) (?P<song_id>\d+)")
	def handle_ph_removesong(self, nick, channel, output, song_id):
		"""Remove a song from this user's Power Hour planning list"""

		self.log.info("%s used !ph removesong" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		song_id = int(song_id)
		m = self._get_song_info_string(song_id)

		if song_id in self.ph.items(nick):
			self.ph.remove(nick, song_id)
			m += " removed from your Power Hour planning list"
		else:
			m += " is not in your Power Hour planning list"

		output.privrs.append(m)

	@command_handler(r"^!ph up (?P<song_id>\d+)")
	def handle_ph_up(self, nick, channel, output, song_id):
		"""Move a song up in this user's Power Hour planning list"""

		self.log.info("%s used !ph up" % nick)
		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !ph" % nick)
			return

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		song_id = int(song_id)
		m = self._get_song_info_string(song_id)

		if song_id in self.ph.items(nick):
			self.ph.up(nick, song_id)
			m += " moved up in your Power Hour planning list"
		else:
			m += " is not in your Power Hour planning list"

		output.privrs.append(m)

	@command_handler(r"!prevplayed(\s(?P<rchan>\w+))?(\s(?P<index>\d))?")
	@command_handler(r"!pp(?P<rchan>\w+)?(\s(?P<index>\d))?")
	def handle_prevplayed(self, nick, channel, output, rchan=None, index=0):
		"""Report what was previously playing on the radio

		Arguments:
			station: station to check
			index: (int) (0, 1, 2) which previously played song, higher number =
				further in the past"""

		self.log.info("%s used !prevplayed" % nick)

		rs = []

		if rchan:
			rchan = rchan.lower()
		else:
			cur_cid = self._get_current_channel_for_nick(nick)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				output.privrs.append("I cannot determine the channel")
				self.handle_help(nick, channel, output, topic="prevplayed")
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic="prevplayed")
			return
		rchn = self.channel_names[cid]

		try:
			index = int(index)
		except TypeError:
			index = 0
		if index not in [0, 1, 2]:
			self.handle_help(nick, channel, output, topic="prevplayed")
			return

		data = self.rw.get_timeline(cid)
		sched_id = data["sched_history"][index]["sched_id"]
		sched_type = data["sched_history"][index]["sched_type"]
		if sched_type in (0, 4):
			pp = data["sched_history"][index]["song_data"][0]
			album = pp["album_name"]
			song = pp["song_title"]
			arts = pp["artists"]
			art_list = []
			for art in arts:
				art_name = art["artist_name"]
				art_list.append(art_name)
			artt = ", ".join(art_list)
			r = "Previously on the %s: %s / %s by %s" % (rchn, album, song, artt)

			if "elec_votes" in pp:
				votes = pp["elec_votes"]
			else:
				votes = 0
			avg = pp["song_rating_avg"]

			r += " (%s vote" % votes
			if votes <> 1:
				r += "s"
			r += ", rated %s" % avg

			type = pp["elec_isrequest"]
			if type in (3, 4):
				r += ", requested by %s" % pp["song_requestor"]
			elif type in (0, 1):
				r += ", conflict"
			r += ")"
			rs.append(r)
		else:
			r = "%s: I have no idea (sched_type = %s)" % (rchn, sched_type)
			rs.append(r)

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		if sched_id == int(self.config.get("pp:%s:%s" % (cid, index))):
			output.privrs.extend(rs)
			r = "I am cooling down. You can only use !prevplayed in "
			r += "%s once per song." % channel
			output.privrs.append(r)
		else:
			output.default.extend(rs)
			self.config.set("pp:%s:%s" % (cid, index), sched_id)

	@command_handler(r"^!rate(\s(?P<rchan>\w+))?(\s(?P<rating>\w+))?")
	@command_handler(r"^!rt(?P<rchan>\w+)?(\s(?P<rating>\w+))?")
	def handle_rate(self, nick, channel, output, rchan=None, rating=None):
		"""Rate the currently playing song

		Arguments:
			rchan: station of song to rate
			rating: the rating"""

		self.log.info("%s used !rate" % nick)

		# Make sure this nick matches a username
		user_id = self.config.get_id_for_nick(nick)

		if not user_id and self.rwdb:
			user_id = self.rwdb.get_id_for_nick(nick)

		if not user_id:
			r = "I do not have a user id stored for you. Visit "
			r += "http://rainwave.cc/auth/ to look up your user id and tell me "
			r += "about it with \x02!id add <id>\x02"
			output.privrs.append(r)
			return

		# Get the key for this user
		key = self.config.get_key_for_nick(nick)
		if not key:
			r = "I do not have a key stored for you. Visit "
			r += "http://rainwave.cc/auth/ to get a key and tell me about it "
			r += "with \x02!key add <key>\x02"
			output.privrs.append(r)
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
				output.privrs.append("I cannot determine the channel")
				self.handle_help(nick, channel, output, topic="rate")
				return

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
		else:
			self.handle_help(nick, channel, output, topic="prevplayed")
			return

		# Get the song_id
		data = self.rw.get_timeline(cid)
		song_id = data["sched_current"]["song_data"][0]["song_id"]

		# Try the rate
		data = self.rw.rate(cid, song_id, rating, user_id, key)

		if "rate_result" in data:
			output.privrs.append(data["rate_result"]["text"])
		else:
			output.privrs.append(data["error"]["text"])

	@command_handler(r"^!refresh(\s(?P<rchan>\w+))?")
	def handle_refresh(self, nick, channel, output, rchan=None):
		"""See the status of or initiate a playlist refresh"""

		self.log.info("%s used !refresh" % nick)

		if not self._is_admin(nick):
			self.log.warning("%s does not have privs to use !refresh" % nick)
			return

		# This command requires the Rainwave database

		if self.rwdb is None:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		if rchan:
			rchan = rchan.lower()

		if rchan in self.channel_ids:
			cid = self.channel_ids.get(rchan)
			self.rwdb.request_playlist_refresh(cid)

		for pending in self.rwdb.get_pending_refresh_jobs():
			output.privrs.append("Pending playlist refresh on the %s." %
				self.channel_names[pending])

		for running in self.rwdb.get_running_refresh_jobs():
			output.privrs.append("Running playlist refresh on the %s." %
				self.channel_names[self.channel_ids.get(running)])

		if len(output.privrs) == 0:
			output.privrs.append("No pending or running playlist refresh jobs.")

	@command_handler(r"^!request(\s(?P<rchan>\w+))?(\s(?P<songid>\d+))?")
	@command_handler(r"^!rq(?P<rchan>\w+)?(\s(?P<songid>\d+))?")
	def handle_request(self, nick, channel, output, rchan=None, songid=None):
		"""Request a song on the radio

		Arguments:
			station: the station to request on
			songid: id of song to request"""

		self.log.info("%s used !request" % nick)

		if rchan is None:
			if songid is None:
				self.handle_help(nick, channel, output, topic="request")
				return
			rchan = 0
		else:
			rchan = rchan.lower()
			if songid is None:
				songid = rchan

		if rchan not in self.channel_ids:
			luid = self.config.get_id_for_nick(nick)
			if not luid and self.rwdb:
				luid = self.rwdb.get_id_for_nick(nick)
			cur_cid = self.rwdb.get_current_channel(luid)
			if cur_cid:
				rchan = self.channel_codes[cur_cid]
			else:
				self.handle_help(nick, channel, output, topic="request")
				return

		cid = self.channel_ids.get(rchan)

		user_id = self.config.get_id_for_nick(nick)

		if not user_id and self.rwdb:
			user_id = self.rwdb.get_id_for_nick(nick)

		if not user_id:
			r = "I do not have a user id stored for you. Visit "
			r += "http://rainwave.cc/auth/ to look up your user id and tell me "
			r += "about it with \x02!id add <id>\x02"
			output.privrs.append(r)
			return

		key = self.config.get_key_for_nick(nick)
		if not key:
			r = "I do not have a key stored for you. Visit "
			r += "http://rainwave.cc/auth/ to get a key and tell me about it "
			r += "with \x02!key add <key>\x02"
			output.privrs.append(r)
			return

		data = self.rw.request(cid, songid, user_id, key)

		if "request_result" in data:
			output.privrs.append(data["request_result"]["text"])
		else:
			output.privrs.append(data["error"]["text"])

	@command_handler("!restart")
	def handle_restart(self, nick, channel, output):
		"""Restart the bot"""

		self.log.info("%s used !restart" % nick)

		if self._is_admin(nick):
			self.config.set("restart_on_stop", 1)
			self.handle_stop(nick, channel, output)
		else:
			self.log.warning("%s does not have privs to use !restart" % nick)

	@command_handler("!roll(\s(?P<dice>\d+)(d(?P<sides>\d+))?)?")
	def handle_roll(self, nick, channel, output, dice=None, sides=None):
		"""Roll some dice"""

		self.log.info("%s used !roll" % nick)

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

		r = "%sd%s: " % (dice, sides)
		if dice > 1 and dice < 11:
			r += "[" + ", ".join(map(str, rolls)) + "] = "
		r += "%s" % sum(rolls)

		if channel == PRIVMSG:
			output.default.append(r)
			return

		ltr = int(self.config.get("lasttime:roll", 0))
		wr = int(self.config.get("wait:roll", 0))
		if ltr < time.time() - wr:
			output.default.append(r)
			self.config.set("lasttime:roll", time.time())
		else:
			output.privrs.append(r)
			wait = ltr + wr - int(time.time())
			r = "I am cooling down. You cannot use !roll in "
			r += "%s for another %s seconds." % (channel, wait)
			output.privrs.append(r)

	@command_handler(r"!(?P<mode>rock|paper|scissors)")
	def handle_rps(self, nick, channel, output, mode=None):
		"""Rock, paper, scissors"""

		if mode is None:
			return
		else:
			mode = mode.lower()

		self.log.info("%s used !%s" % (nick, mode))

		rps = ["rock", "paper", "scissors"]
		challenge	 = rps.index(mode)
		response = random.randint(0, 2)

		self.config.log_rps(nick, challenge, response)

		r = "You challenge with %s. I counter with %s. " % (mode, rps[response])

		if challenge == (response + 1) % 3:
			r += "You win!"
		elif challenge == response:
			r += "We draw!"
		elif challenge == (response + 2) % 3:
			r+= "You lose!"

		w, d, l = self.config.get_rps_record(nick)
		pw = int(float(w)/float(w+d+l)*100)
		pd = int(float(d)/float(w+d+l)*100)
		pl = int(float(l)/float(w+d+l)*100)
		r += " Your current record is %s-%s-%s or %s%%-%s%%-%s%% (w-d-l)." % (w, d, l, pw, pd, pl)

		if channel == PRIVMSG:
			output.default.append(r)
			return

		ltr = int(self.config.get("lasttime:rps", 0))
		wr = int(self.config.get("wait:rps", 0))
		if ltr < time.time() - wr:
			output.default.append(r)
			self.config.set("lasttime:rps", time.time())
		else:
			output.privrs.append(r)
			wait = ltr + wr - int(time.time())
			r = "I am cooling down. You cannot use !%s in %s " % (mode, channel)
			r += "for another %s seconds." % wait
			output.privrs.append(r)

	@command_handler(r"^!rps record(\s(?P<target>\S+))?")
	def handle_rps_record(self, nick, channel, output, target=None):
		"""Report RPS record for a nick"""

		self.log.info("%s used !rps record" % nick)

		if target is None:
			target = nick

		w, d, l = self.config.get_rps_record(target)
		total = sum((w, d, l))
		r = "RPS record for %s (%s game" % (target, total)
		if total != 1:
			r += "s"
		r += ") is %s-%s-%s (w-d-l)." % (w, d, l)

		if channel == PRIVMSG:
			output.default.append(r)
			return

		ltr = int(self.config.get("lasttime:rps", 0))
		wr = int(self.config.get("wait:rps", 0))
		if ltr < time.time() - wr:
			output.default.append(r)
			self.config.set("lasttime:rps", time.time())
		else:
			output.privrs.append(r)
			wait = ltr + wr - int(time.time())
			output.privrs.append("I am cooling down. You cannot use !rps in %s "
				"for another %s seconds." % (channel, wait))

	@command_handler(r"!rps rename(\s(?P<old>\S+))?(\s(?P<new>\S+))?")
	def handle_rps_rename(self, nick, channel, output, old=None, new=None):
		"""Rename an RPS nick, useful for merging game histories"""

		self.log.info("%s used !rps rename" % nick)

		if self._is_admin(nick) and old and new:
			self.config.rename_rps_player(old, new)
			r = "I assigned the RPS game history for %s to %s." % (old, new)
			output.privrs.append(r)

	@command_handler(r"^!rps reset")
	def handle_rps_reset(self, nick, channel, output):
		"""Reset RPS stats and delete game history for a nick"""

		self.log.info("%s used !rps reset" % nick)

		self.config.reset_rps_record(nick)
		r = "I reset your RPS record and deleted your game history."
		output.privrs.append(r)

	@command_handler(r"!rps stats(\s(?P<target>\S+))?")
	def handle_rps_stats(self, nick, channel, output, target=None):
		"""Get some RPS statistics for a player"""

		self.log.info("%s used !rps stats" % nick)

		if target is None:
			target = nick

		totals = self.config.get_rps_challenge_totals(target)
		games = sum(totals)
		if games > 0:
			r_rate = totals[0] / float(games) * 100
			p_rate = totals[1] / float(games) * 100
			s_rate = totals[2] / float(games) * 100

			r = ("%s challenges with rock/paper/scissors at these rates: "
				"%3.1f/%3.1f/%3.1f%%." % (target, r_rate, p_rate, s_rate))
		else:
			r = "%s does not play. :(" % target

		if channel == PRIVMSG:
			output.default.append(r)
			return

		ltr = int(self.config.get("lasttime:rps", 0))
		wr = int(self.config.get("wait:rps", 0))
		if ltr < time.time() - wr:
			output.default.append(r)
			self.config.set("lasttime:rps", time.time())
		else:
			output.privrs.append(r)
			wait = ltr + wr - int(time.time())
			output.privrs.append("I am cooling down. You cannot use !rps in %s "
				"for another %s seconds." % (channel, wait))

	@command_handler(r"^!rps who")
	def handle_rps_who(self, nick, channel, output):
		"""List all players in the RPS game history"""

		self.log.info("%s used !rps who" % nick)

		rs = []
		players = self.config.get_rps_players()

		mlnl = int(self.config.get("maxlength:nicklist", 10))
		while len(players) > mlnl:
			plist = players[:mlnl]
			players[:mlnl] = []
			r = "RPS players: " + ", ".join(plist)
			rs.append(r)
		r = "RPS players: " + ", ".join(players)
		rs.append(r)

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		ltr = int(self.config.get("lasttime:rps", 0))
		wr = int(self.config.get("wait:rps", 0))
		if ltr < time.time() - wr:
			output.default.extend(rs)
			self.config.set("lasttime:rps", time.time())
		else:
			output.privrs.extend(rs)
			wait = ltr + wr - int(time.time())
			output.privrs.append("I am cooling down. You cannot use !rps in %s "
				"for another %s seconds." % (channel, wait))

	@command_handler(r"^!set(\s(?P<id>\S+))?(\s(?P<value>.+))?")
	def handle_set(self, nick, channel, output, id=None, value=None):
		"""View and set bot configuration"""
		
		self.log.info("%s used !set" % nick)
		
		if self._is_admin(nick):
			output.privrs.extend(self.config.handle(id, value))
		else:
			self.log.warning("%s does not have privs to use !set" % nick)
			self.handle_help(nick, channel, output, topic="set")

	@command_handler(r"!stats(\s(?P<rchan>\w+))?")
	def handle_stats(self, nick, channel, output, rchan=None):
		"""Report radio statistics"""

		self.log.info("%s used !stats" % nick)

		if rchan:
			rchan = rchan.lower()

		cid = self.channel_ids.get(rchan, 0)
		if self.rwdb:
			songs, albums, hours = self.rwdb.get_radio_stats(cid)
			r = ("%s: %s songs in %s albums with %s hours of music." %
				(self.channel_names[cid], songs, albums, hours))
		else:
			r = "The Rainwave database is unavailable."

		if channel == PRIVMSG:
			output.default.append(r)
			return

		lts = int(self.config.get("lasttime:stats", 0))
		ws = int(self.config.get("wait:stats", 0))
		if lts < time.time() - ws:
			output.default.append(r)
			self.config.set("lasttime:stats", time.time())
		else:
			output.privrs.append(r)
			wait = lts + ws - int(time.time())
			output.privrs.append("I am cooling down. You cannot use !stats in "
				"%s for another %s seconds." % (channel, wait))

	@command_handler("!stop")
	def handle_stop(self, nick, channel, output):
		"""Shut down the bot"""

		self.log.info("%s used !stop" % nick)

		if self._is_admin(nick):
			if self.config.get("restart_on_stop"):
				self.config.unset("restart_on_stop")
				pid = subprocess.Popen([_abspath, "5"], stdout=subprocess.PIPE,
					stderr=subprocess.PIPE, stdin=subprocess.PIPE)
			self.die("I was stopped by %s" % nick)
		else:
			self.log.warning("%s does not have privs to use !stop" % nick)

	@command_handler(r"!unrated(\s(?P<rchan>\w+))?(\s(?P<num>\d+))?")
	def handle_unrated(self, nick, channel, output, rchan=None, num=None):
		"""Report unrated songs"""

		self.log.info("%s used !unrated" % nick)

		if rchan is None:
			self.handle_help(nick, channel, output, topic="unrated")
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
				self.handle_help(nick, channel, output, topic="unrated")
				return

		cid = self.channel_ids.get(rchan)

		try:
			num = int(num)
		except:
			num = 1

		user_id = self.config.get_id_for_nick(nick)
		if not user_id and self.rwdb:
			user_id = self.rwdb.get_id_for_nick(nick)

		if not user_id:
			output.privrs.append("I do not have a user id stored for you. "
				"Visit http://rainwave.cc/auth/ to look up your user id and "
				"tell me about it with \x02!id add <id>\x02")
			return

		if not self.rwdb:
			output.privrs.append("The Rainwave database is unavailable.")
			return

		unrated = self.rwdb.get_unrated_songs(user_id, cid, num)
		for ucid, text in unrated:
			uchn = self.channel_names[ucid]
			output.privrs.append("%s: %s" % (uchn, text))

	@command_handler(r"^!unset(\s(?P<id>\S+))?")
	def handle_unset(self, nick, channel, output, id=None):
		"""Unset a configuration item"""
		
		self.log.info("%s used !unset" % nick)
		
		if self._is_admin(nick):
			if id:
				self.config.unset(id)
				output.privrs.append("%s has been unset" % id)
				return
		else:
			self.log.warning("%s does not have privs to use !unset" % nick)

		self.handle_help(nick, channel, output, topic="unset")

	@command_handler(r"!ustats(\s(?P<target>.+))?")
	def handle_ustats(self, nick, channel, output, target=None):
		"""Report user statistics"""

		self.log.info("%s used !ustats" % nick)

		rs = []

		if target is None:
			target = nick

		luid = self.config.get_id_for_nick(target)
		if not luid and self.rwdb:
			luid = self.rwdb.get_id_for_nick(target)
		if not luid:
			output.default.append("I do not recognize the username '%s'." % target)
			return

		uid = self.config.get("api:user_id", 0)
		key = self.config.get("api:key", 0)
		data = self.rw.get_listener(luid, uid, key)

		if "listener_detail" in data:
			ld = data["listener_detail"]
			cun = ld["username"] # canonical username

			# Line 1: winning/losing votes/requests

			wvotes = ld["radio_winningvotes"]
			lvotes = ld["radio_losingvotes"]
			wreqs = ld["radio_winningrequests"]
			lreqs = ld["radio_losingrequests"]
			tvotes = ld["radio_2wkvotes"]
			r = "%s has %s winning vote" % (cun, wvotes)
			if wvotes != 1:
				r += "s"
			r += ", %s losing vote" % lvotes
			if lvotes != 1:
				r += "s"
			r += ", %s winning request" % wreqs
			if wreqs != 1:
				r += "s"
			r += ", %s losing request" % lreqs
			if lreqs != 1:
				r += "s"
			r += " (%s vote" % tvotes
			if tvotes != 1:
				r += "s"
			r += " in the last two weeks)."
			rs.append(r)

			# Line 2: rating progress

			game = ld["user_station_specific"]["1"]["rating_progress"]
			ocr = ld["user_station_specific"]["2"]["rating_progress"]
			cover = ld["user_station_specific"]["3"]["rating_progress"]
			chip = ld["user_station_specific"]["4"]["rating_progress"]
			r = "%s has rated %d%% of Game" % (cun, game)
			r += ", %d%% of OCR, %d%% of Covers" % (ocr, cover)
			r += ", %d%% of Chiptune channel content." % chip
			rs.append(r)

			# Line 3: What channel are you listening to?

			cur_cid = self.rwdb.get_current_channel(luid)
			if cur_cid:
				rch = self.channel_names[cur_cid]
				r = "%s is currently listening to the %s." % (cun, rch)
				rs.append(r)
		else:
			rs.append(data["error"]["text"])

		if channel == PRIVMSG:
			output.default.extend(rs)
			return

		ltu = int(self.config.get("lasttime:ustats", 0))
		wu = int(self.config.get("wait:ustats", 0))
		if ltu < time.time() - wu:
			output.default.extend(rs)
			self.config.set("lasttime:ustats", time.time())
		else:
			output.privrs.extend(rs)
			wait = ltu + wu - int(time.time())
			output.privrs.append("I am cooling down. You cannot use !ustats in "
				"%s for another %s seconds." % (channel, wait))

	@command_handler(r"!vote(\s(?P<rchan>\w+))?(\s(?P<index>\d+))?")
	@command_handler(r"!vt(?P<rchan>\w+)?(\s(?P<index>\d+))?")
	def handle_vote(self, nick, channel, output, rchan=None, index=None):
		"""Vote in the current election"""

		self.log.info("%s used !vote" % nick)

		if rchan is None:
			if index is None:
				self.handle_help(nick, channel, output, topic="vote")
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
				output.privrs.append("Either you are not tuned in or your IRC "
					"nick does not match your forum username. Tune in to a "
					"channel or link your Rainwave account to this IRC nick "
					"using \x02!id\x02.")
				return
		
		cid = self.channel_ids.get(rchan)

		try:
			index = int(index)
		except:
			self.handle_help(nick, channel, output, topic="vote")
			return

		if index not in [1, 2, 3]:
			self.handle_help(nick, channel, output, topic="vote")
			return

		user_id = self.config.get_id_for_nick(nick)

		if not user_id and self.rwdb:
			user_id = self.rwdb.get_id_for_nick(nick)

		if not user_id:
			output.privrs.append("I do not have a user id stored for you. "
				"Visit http://rainwave.cc/auth/ to look up your user id and "
				"tell me about it with \x02!id add <id>\x02")
			return

		# Get the key for this user

		key = self.config.get_key_for_nick(nick)
		if not key:
			output.privrs.append("I do not have a key stored for you. Visit "
				"http://rainwave.cc/auth/ to get a key and tell me about it "
				"with \x02!key add <key>\x02")
			return

		# Get the elec_entry_id

		data = self.rw.get_timeline(cid)
		voteindex = index - 1
		song_data = data["sched_next"][0]["song_data"]
		elec_entry_id = song_data[voteindex]["elec_entry_id"]

		# Try the vote

		data = self.rw.vote(cid, elec_entry_d, user_id, key)

		if data["vote_result"]:
			output.privrs.append(data["vote_result"]["text"])
		else:
			output.privrs.append(data["error"]["text"])

	def on_join(self, c, e):
		"""This method is called when an IRC join event happens

		Arguments:
			c: the Connection object asociated with this event
			e: the Event object"""

		nick = e.source().split("!")[0]
		irc_chan = e.target()

		# Check for a join response
		jr = self.config.get("joinresponse:%s" % nick)
		if jr:
			self._to_irc(c, "privmsg", irc_chan, jr)

		ja = self.config.get("joinaction:%s" % nick)
		if ja:
			self._to_irc(c, "action", irc_chan, ja)

	def on_ping(self, c, e):
		"""This method is called when an IRC ping event happens"""

		# Start the periodic tasks.
		self._periodic(c)

	def on_privmsg(self, c, e):
		"""This method is called when a message is sent directly to the bot

		Arguments:
			c: the Connection object associated with this event
			e: the Event object"""

		nick = e.source().split("!")[0]
		msg = e.arguments()[0].strip()
		try:
			msg = unicode(msg, "utf-8")
		except UnicodeDecodeError:
			self.log.exception("Cannot convert message to unicode")
			return

		rs = []
		privrs = []

		# Try all the command handlers

		output = Output("private")
		for command in _commands:
			if command(self, nick, msg, PRIVMSG, output):
				rs = output.rs
				privrs = output.privrs
				break

		if len(rs) + len(privrs) == 0:
			# No responses from the commands, punt to the brain

			privrs.extend(self._talk(msg))

		# Send responses

		channel = self.config.get("irc:channel")
		for r in rs:
			self._to_irc(c, "privmsg", channel, r)

		for privr in privrs:
			self._to_irc(c, "privmsg", nick, privr)

	def on_pubmsg(self, c, e):
		"""This method is called when a message is sent to the channel the bot
		is on

		Arguments:
			c: the Connection object associated with this event
			e: the Event object"""

		nick = e.source().split("!")[0]
		chan = e.target()
		msg = e.arguments()[0].strip()
		try:
			msg = unicode(msg, "utf-8")
		except UnicodeDecodeError:
			self.log.exception("Cannot convert message to unicode")
			return

		rs = []
		privrs = []

		# Try all the command handlers

		output = Output("public")
		for command in _commands:
			if command(self, nick, msg, chan, output):
				rs = output.rs
				privrs = output.privrs
				break

		# If there are no responses from the commands, look for URLs

		if len(rs) + len(privrs) == 0:
			urls = self._find_urls(msg)
			for url in urls:
				title = self._get_title(url)
				if title:
					self.log.info("Found a title: %s" % title)
					rs.append("[ %s ]" % title)

		# If there are no URLs, punt to the brain

		if len(rs) + len(privrs) == 0:
			talkrs = self._talk(msg)
			if len(talkrs) > 0:
				self.config.set("msg:last", msg)
				self.config.set("lasttime:msg", time.time())
				ltr = int(self.config.get("lasttime:respond", 0))
				wr = int(self.config.get("wait:respond", 0))

				if self.config.get("irc:nick") in msg:
					if time.time() > ltr + wr:
						rs.extend(talkrs)
						self.config.set("msg:last", talkrs[0])
						self.config.set("lasttime:respond", time.time())
					else:
						privrs.extend(talkrs)
						wait = ltr + wr - int(time.time())
						privrs.append("I am cooling down. I cannot respond in "
							"%s for another %s seconds." % (chan, wait))

		# Send responses

		for r in rs:
			r = nick + ": " + r
			self._to_irc(c, "privmsg", chan, r)

		for privr in privrs:
			self._to_irc(c, "privmsg", nick, privr)

	def on_topic(self, c, e):
		"""This method is called when the topic is set

		Arguments:
			c: the Connection object associated with this event
			e: the Event object"""

		nickmask = e.source()
		nick = nickmask.split("!")[0]
		new_topic = e.arguments()[0]
		m = "%s changed the topic to: %s" % (nick, new_topic)

		nicks_to_match = self.config.get("funnytopic:nicks", "").split()
		if nick in nicks_to_match:
			forum_id = self.config.get("funnytopic:forum_id")
			if forum_id is None:
				self.log.warning("Please !set funnytopic:forum_id")
				return
			topic_id = self.config.get("funnytopic:topic_id")
			if topic_id is None:
				self.log.warning("Please !set funnytopic:topic_id")
				return
			self._post_to_forum(forum_id, topic_id, m)

	def on_welcome(self, c, e):
		"""This method is called when the bot first connects to the server

		Arguments:
			c: the Connection object associated with this event
			e: the Event object"""

		passwd = self.config.get("irc:nickservpass")
		self._to_irc(c, "privmsg", "nickserv", "identify %s" % passwd)
		c.join(self.config.get("irc:channel"))

	def _find_urls(self, text):
		"""Look for URLs in arbitrary text. Return a list of the URLs found."""

		self.log.info("Looking for URLs in: %s" % text)

		urls = []
		for token in text.split():
			o = urlparse(token)
			if "http" in o.scheme and o.netloc:
				url = o.geturl()
				self.log.info("Found a URL: %s" % url)
				urls.append(url)
		return urls

	def _get_current_channel_for_nick(self, nick):
		"""Try to find the channel that `nick` is currently tuned in to. Return
		a numeric channel id or None."""

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
		"""Get song info as single string"""
		
		info = self.rwdb.get_song_info(song_id)
		info["chan"] = self.channel_names[info["chan_id"]]
		m = u"{chan} // {album} [{album_id}] // {title} [{id}]".format(**info)
		return m

	def _get_title(self, url):
		"""Attempt to get the page title from a URL"""

		ua = "wormgas/0.1 +http://github.com/subtlecoolness/wormgas"
		rq = urllib2.Request(url)
		rq.add_header('user-agent', ua)
		op = urllib2.build_opener()

		try:
			data = op.open(rq)
		except:
			self.log.exception("Cannot open the URL: %s" % url)
			return None

		try:
			title = lxml.html.parse(data).findtext("head/title")
		except:
			self.log.exception("Cannot parse the page at: %s" % url)
			return None

		if title:
			title = " ".join(title.split())
		return title

	def _is_admin(self, nick):
		"""Check whether a nick has privileges to use administrative commands"""

		channel = self.config.get("irc:channel").encode('ascii')
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
		# If I have not checked for forum activity for "timeout:forumcheck"
		# seconds, check now

		self.log.info("Performing periodic tasks")

		nick = self.config.get("irc:nick")
		chan = self.config.get("irc:channel")
		output = Output("public")

		ltfc = int(self.config.get("lasttime:forumcheck", 0))
		tofc = int(self.config.get("timeout:forumcheck", 3600))
		if int(time.time()) > ltfc + tofc:
			self.log.info("Forum check timeout exceeded")
			self.handle_forum(nick, chan, output, force=False)

		ltmc = int(self.config.get("lasttime:musiccheck", 0))
		tomc = int(self.config.get("timeout:musiccheck", 3600))
		if int(time.time()) > ltmc + tomc:
			self.log.info("Music check timeout exceeded")
			for rchan in self.channel_ids.keys():
				self.handle_newmusic(nick, chan, output, rchan=rchan, force=False)

		ltm = int(self.config.get("lasttime:msg", 0))
		toc = int(self.config.get("timeout:chat", 3600))
		if int(time.time()) > ltm + toc:
			self.log.info("Chat timeout exceeded, keep the conversation moving")
			talkrs = self._talk()
			for talkr in talkrs:
				self.config.set("msg:last", talkr)
				self.config.set("lasttime:msg", time.time())
				self.config.set("lasttime:respond", time.time())
				output.rs.append(talkr)

		for r in output.rs:
			self._to_irc(c, "privmsg", chan, r)

	def _post_to_forum(self, forum_id, topic_id, m):
		"""Post a message to the phpBB forum

		Arguments:
			forum_id: phpBB forum id where the message should be sent
			topic_id: phpBB topic id where the message should be sent (cannot create
				new topics)
			m: message to be sent"""

		url = self.config.get("funnytopic:url")
		if url is None:
			self.log.warning("Please !set funnytopic:url")
			return

		u = self.config.get("funnytopic:username")
		if u is None:
			self.log.warning("Please !set funnytopic:username")
			return

		p = self.config.get("funnytopic:password")
		if p is None:
			self.log.warning("Please !set funnytopic:password")
			return

		m = m.replace("<", "&lt;").replace(">", "&gt;")

		post_data = {"u": u, "p": p, "f": forum_id, "t": topic_id, "m": m}
		urllib2.urlopen(url, urllib.urlencode(post_data))

	def _shorten(self, lurl):
		"""Shorten a URL

		Arguments:
			lurl: The long url

		Returns: a string, the short url"""

		body = json.dumps({"longUrl": lurl})
		headers = {}
		headers["content-type"] = "application/json"
		ua = "wormgas/0.1 +http://github.com/subtlecoolness/wormgas"
		headers["user-agent"] = ua

		h = httplib.HTTPSConnection("www.googleapis.com")
		gkey = self.config.get("googleapikey")
		gurl = "/urlshortener/v1/url?key=%s" % gkey
		h.request("POST", gurl, body, headers)
		content = h.getresponse().read()

		result = json.loads(content)
		if "id" in result:
			return result["id"]
		
		return ""

	def _talk(self, msg=None):
		"""Engage the brain, respond when appropriate

		Arguments:
			msg: the message to learn and possible reply to

		Returns: a list of strings"""

		# If I am not replying to anything in particular, use the last message
		if msg is None:
			msg = self.config.get("msg:last")
		if msg is None:
			return []

		# Ignore messages with certain words
		if self.reignore:
			result = self.reignore.search(msg)
			if result is not None:
				return []

		# Clean up the message before sending to the brain
		tobrain = msg
		tobrain = tobrain.replace(self.config.get("irc:nick"), "")
		tobrain = tobrain.replace(":", "")

		self.brain.learn(tobrain)

		return [self.brain.reply(tobrain)]

	def _to_irc(self, c, msgtype, target, msg):
		"""Send an IRC message"""

		self.log.debug("Sending %s to %s -- %s" % (msgtype, target, msg))

		if hasattr(c, msgtype):
			f = getattr(c, msgtype)
			if type(msg) is not unicode:
				msg = unicode(msg, "utf-8")
			try:
				f(target, msg.encode("utf-8"))
			except:
				self.log.exception("Problem sending to IRC")
		else:
			self.log.error("Invalid message type '%s'" % msgtype)

def main():
		try:
				pid = os.fork()
				if pid > 0:
						sys.exit(0)
		except (OSError, AttributeError):
				pass # Non-Unix systems will run wormgas in the foreground.

		if len(sys.argv) > 1:
				sleeptime = float(sys.argv[1])
		else:
				sleeptime = 0
		time.sleep(sleeptime)

		bot = wormgas()
		bot.start()

if __name__ == "__main__":
		main()
