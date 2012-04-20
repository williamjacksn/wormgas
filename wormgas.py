#!/usr/bin/python
"""
wormgas -- IRC bot for Rainwave (http://rainwave.cc)
https://github.com/subtlecoolness/wormgas
"""

import gzip
import httplib
import json
import lxml.html
import logging, logging.handlers
import math
import os
import random
import re
import StringIO
import subprocess
import sys
import threading
import time
import urllib, urllib2
from urlparse import urlparse

import dbaccess
from ircbot import SingleServerIRCBot
from cobe.brain import Brain

_abspath = os.path.abspath(__file__)

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

_commands = set()

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
            return func(self, nick, channel, output, **result.groupdict())
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

    log = logging.getLogger("wormgas")

    def __init__(self):
        (self.path, self.file) = os.path.split(_abspath)

        self.config = dbaccess.Config(self.path)

        try:
            self.rwdb = dbaccess.RainwaveDatabase(self.config)
            self.rwdb.connect()
        except dbaccess.RainwaveDatabaseUnavailableError:
            self.rwdb = None

        self.brain = Brain(self.path + "/brain.sqlite")
        self.reignore = re.compile(self.config.get("msg:ignore"))

        server = self.config.get("irc:server")
        nick = self.config.get("irc:nick")
        name = self.config.get("irc:name")
        SingleServerIRCBot.__init__(self, [(server, 6667)], nick, name)

    _events_not_logged = [
        "all_raw_messages",
        "created",
        "endofmotd",
        "endofnames",
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
        "n_local",
        "namreply"
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
            return True

        # Otherwise, check for the cooldown and respond accordingly.
        ltb = int(self.config.get("lasttime:8ball"))
        wb = int(self.config.get("wait:8ball"))
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
        return True

    @command_handler(r"^!config(\s(?P<id>\S+))?(\s(?P<value>.+))?")
    def handle_config(self, nick, channel, output, id=None, value=None):
        """View and set config items"""

        self.log.info("%s used !config" % nick)

        priv = int(self.config.get("privlevel:%s" % nick))
        if priv > 1:
            output.privrs.extend(self.config.handle(id, value))
        else:
            self.log.warning("%s does not have privs to use !config" % nick)
        return True

    @command_handler(r"^!c(ool)?d(own)? add(\s(?P<unit>\w+))?"
        r"(\s(?P<unit_id>\d+))?(\s(?P<cdg_name>.+))?")
    def handle_cooldown_add(self, nick, channel, output, unit=None,
        unit_id=None, cdg_name=None):
        """Add a song or album to a cooldown group."""

        self.log.info("%s used !cooldown add" % nick)
        self.log.info("unit: %s, unit_id: %s, cdg_name: %s" % (unit, unit_id,
            cdg_name))

        # This command requires privlevel 1

        priv = self.config.get("privlevel:%s" % nick)
        if priv < 1:
            self.log.warning("%s does not have privs to use !cooldown add" %
                nick)
            return True

        # This command requires the Rainwave database

        if self.rwdb is None:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        # cdg_name must be specified

        if cdg_name is None:
            return self.handle_help(nick, channel, output, topic="cooldown")

        # unit_id should be numeric

        if unit_id is None:
            return self.handle_help(nick, channel, output, topic="cooldown")

        if unit_id.isdigit():
            unit_id = int(unit_id)
        else:
            return self.handle_help(nick, channel, output, topic="cooldown")

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
            return self.handle_help(nick, channel, output, topic="cooldown")

        return True

    @command_handler(r"^!c(ool)?d(own)? drop(\s(?P<unit>\w+))?"
        r"(\s(?P<unit_id>\d+))?(\s(?P<cdg_name>.+))?")
    def handle_cooldown_drop(self, nick, channel, output, unit=None,
        unit_id=None, cdg_name=None):
        """Remove a song or album from a cooldown group"""

        self.log.info("%s used !cooldown drop" % nick)
        self.log.info("unit: %s, unit_id: %s, cdg_name: %s" % (unit, unit_id,
            cdg_name))

        # This command requires privlevel 1

        priv = self.config.get("privlevel:%s" % nick)
        if priv < 1:
            self.log.warning("%s does not have privs to use !cooldown add" %
                nick)
            return True

        # This command requires the Rainwave database

        if self.rwdb is None:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        # unit_id should be numeric

        if unit_id is None:
            return self.handle_help(nick, channel, output, topic="cooldown")

        if unit_id.isdigit():
            unit_id = int(unit_id)
        else:
            return self.handle_help(nick, channel, output, topic="cooldown")

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
                rcode, rval = self.rwdb.drop_song_from_cdg_by_name(unit_id,
                    cdg_name)
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
                rcode, rval = self.rwdb.drop_album_from_cdg_by_name(unit_id,
                    cdg_name)
                if rcode == 0:
                    rchan = self.channel_names[rval[0]]
                    rval = (rchan,) + rval[1:]
                    r = "Dropped %s / %s from cooldown group %s" % rval
                    output.privrs.append(r)
                else:
                    output.privrs.append(rval)
        else:
            return self.handle_help(nick, channel, output, topic="cooldown")

        return True

    @command_handler(r"!el(ection\s)?(?P<rchan>\w+)?(\s(?P<index>\d))?")
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
            return self.handle_help(nick, channel, output, topic="election")

        if rchan is not None:
            rchan = rchan.lower()

        if rchan in self.channel_ids:
            cid = self.channel_ids.get(rchan)
        else:
            return self.handle_help(nick, channel, output, topic="election")

        sched_config = "el:%s:%s" % (cid, index)
        sched_id, text = self._fetch_election(index, cid)

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
        return True

    def _fetch_election(self, index, cid):
        """Return (sched_id, election string) for given index and cid.

        A sched_id is a unique ID given to every scheduled event, including
        elections. The results of this call can therefore be cached locally
        using the sched_id as the cache key.
        """

        data = self.api_call("http://rainwave.cc/async/%s/get" % cid)
        elec = data["sched_next"][index]
        text = ""

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
            return True

        ltf = int(self.config.get("lasttime:flip"))
        wf = int(self.config.get("wait:flip"))
        if ltf < time.time() - wf:
            output.default.append(result)
            self.config.set("lasttime:flip", time.time())
        else:
            output.privrs.append(result)
            wait = ltf + wf - int(time.time())
            r = "I am cooling down. You cannot use !flip in %s " % channel
            r += "for another %s seconds." % wait
            output.privrs.append(r)
        return True

    @command_handler(r"!forum")
    def handle_forum(self, nick, channel, output, force=True):
        """Check for new forum posts, excluding forums where the anonymous user
        has no access"""

        self.log.info("Looking for new forum posts, force is %s" % force)

        priv = self.config.get("privlevel:%s" % nick)
        if priv < 2:
            self.log.warning("%s does not have privs to use !forum" % nick)
            return True

        self.config.set("lasttime:forumcheck", time.time())

        if force:
            self.config.set("maxid:forum", 0)

        maxid = self.config.get("maxid:forum")
        self.log.info("Looking for forum posts newer than %s" % maxid)

        if self.rwdb:
            newmaxid = self.rwdb.get_max_forum_post_id()
        else:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        if newmaxid > int(self.config.get("maxid:forum")):
            r, url = self.rwdb.get_forum_post_info()
            surl = self.shorten(url)
            output.rs.append("New on the forums! %s <%s>" % (r, surl))
            self.config.set("maxid:forum", newmaxid)

        return True

    @command_handler(r"^!help(\s(?P<topic>\w+))?")
    def handle_help(self, nick, channel, output, topic=None):
        """Look up help about a topic"""

        self.log.info("%s used !help" % nick)

        priv = self.config.get("privlevel:%s" % nick)
        rs = []

        channelcodes = ("Channel codes are \x02" +
            "\x02, \x02".join(self.channel_ids.keys()) + "\x02")

        if (topic is None) or (topic == "all"):
            rs.append("Use \x02!help [<topic>]\x02 with one of these topics: "
                "8ball, election, flip, history, id, key, lookup, lstats, "
                "nowplaying, prevplayed, rate, request, roll, rps, stats, "
                "unrated, ustats, vote")
            if priv > 0:
                rs.append("Level 1 administration topics: cooldown, newmusic, "
                    "refresh")
            if priv > 1:
                rs.append("Level 2 administration topics: config, forum, "
                    "restart, stop")
        elif topic == "8ball":
            rs.append("Use \x02!8ball\x02 to ask a question of the magic 8ball")
        elif topic == "config":
            if priv > 1:
                rs.append("Use \x02!config [<id>] [<value>]\x02 to display or "
                    "change configuration settings")
                rs.append("Leave off <value> to see the current setting, or "
                    "use a <value> of -1 to remove a setting")
                rs.append("Leave off <id> and <value> to see a list of all "
                    "available config ids")
            else:
                rs.append("You are not permitted to use this command")
        elif topic == "cooldown":
            if priv > 0:
                rs.append("Use \x02!cooldown add song|album <song_id|album_id> "
                    "<cdg_name>\x02 to add a song or album to a cooldown group")
                rs.append("Use \x02!cooldown drop song|album "
                    "<song_id|album_id> [<cdg_name>]\x02 to remove a song or "
                    "album from a cooldown group, leave off <cdg_name> to "
                    "remove a song or album from all cooldown groups")
                rs.append("Short version is \x02!cd ...\x02")
            else:
                rs.append("You are not permitted to use this command")
        elif topic == "election":
            rs.append("Use \x02!election <channel> [<index>]\x02 to see the "
                "candidates in an election")
            rs.append("Short version is \x02!el<channel> [<index>]\x02")
            rs.append("Index should be 0 (current) or 1 (future), default is 0")
            rs.append(channelcodes)
        elif topic == "flip":
            rs.append("Use \x02!flip\x02 to flip a coin")
        elif topic == "forum":
            if priv > 1:
                rs.append("Use \x02!forum\x02 to announce the most recent "
                    "forum post in the channel")
            else:
                rs.append("You are not permitted to use this command")
        elif topic == "history":
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
        elif topic == "lookup":
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
            if priv > 0:
                rs.append("Use \x02!newmusic <channel>\x02 to announce the "
                    "three most recently added songs on the channel")
                rs.append(channelcodes)
            else:
                rs.append("You are not permitted to use this command")
        elif topic == "nowplaying":
            rs.append("Use \x02!nowplaying <channel>\x02 to show what is "
                "now playing on the radio")
            rs.append("Short version is \x02!np<channel>\x02")
            rs.append(channelcodes)
        elif topic == "prevplayed":
            rs.append("Use \x02!prevplayed <channel> [<index>]\x02 to show "
                "what was previously playing on the radio")
            rs.append("Short version is \x02!pp<channel> [<index>]\x02")
            rs.append("Index should be one of (0, 1, 2), 0 is default, higher "
                "numbers are further in the past")
            rs.append(channelcodes)
        elif topic == "rate":
            rs.append("Use \x02!rate <channel> <rating>\x02 to rate the "
                "currently playing song")
            rs.append("Short version is \x02!rt<channel> <rating>\x02")
            rs.append(channelcodes)
        elif topic == "refresh":
            if priv > 0:
                rs.append("Use \x02!refresh\x02 to show pending or running "
                    "playlist refresh jobs")
                rs.append("Use \x02!refresh <channel>\x02 to request a "
                    "playlist refresh for a particular channel")
                rs.append(channelcodes)
            else:
                rs.append("You are not permitted to use this command")
        elif topic == "request":
            rs.append("Use \x02!request <channel> <song_id>\x02 to add a "
                "song to your request queue, find the <song_id> using "
                "\x02!lookup\x02 or \x02!unrated\x02")
            rs.append("Short version is \x02!rq<channel> <song_id>\x02")
            rs.append(channelcodes)
        elif topic == "restart":
            if priv > 1:
                rs.append("Use \x02!restart\x02 to restart the bot")
            else:
                rs.append("You are not permitted to use this command")
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
            if priv > 1:
                rs.append("Level 2 administrators can use \x02!rps rename "
                    "<oldnick> <newnick>\x02 to reassign stats and game "
                    "history from one nick to another")
        elif topic == "stats":
            rs.append("Use \x02!stats [<channel>]\x02 to show information "
                "about the music collection, leave off <channel> to see the "
                "aggregate for all channels")
            rs.append(channelcodes)
        elif topic == "stop":
            if priv > 1:
                rs.append("Use \x02!stop\x02 to shut down the bot")
            else:
                rs.append("You are not permitted to use this command")
        elif topic == "unrated":
            rs.append("Use \x02!unrated <channel> [<num>]\x02 to see songs "
                "you have not rated, <num> can go up to 12, leave it off to "
                "see just one song")
            rs.append(channelcodes)
        elif topic == "ustats":
            rs.append("Use \x02!ustats [<nick>]\x02 to show user statistics "
                "for <nick>, leave off <nick> to see your own statistics")
        elif topic == "vote":
            rs.append("Use \x02!vote <channel> <index>\x02 to vote in the "
                "current election, find the <index> with \x02!election\x02")
            rs.append(channelcodes)
        else:
            rs.append("I cannot help you with '%s'" % topic)

        output.privrs.extend(rs)
        return True

    @command_handler(r"!history(\s(?P<rchan>\w+))?")
    @command_handler(r"!hs(?P<rchan>\w+)?")
    def handle_history(self, nick, channel, output, rchan=None):
        """Show the last several songs that played on the radio"""

        self.log.info("%s used !history" % nick)

        if self.rwdb is None:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        if rchan is not None:
            rchan = rchan.lower()

        if rchan in self.channel_ids:
            cid = self.channel_ids.get(rchan)
        else:
            return self.handle_help(nick, channel, output, topic="history")
        rchn = self.channel_names[cid]

        for song in self.rwdb.get_history(cid):
            r = "%s: %s -- %s [%s] / %s [%s]" % ((rchn,) + song)
            output.privrs.append(r)

        output.privrs.reverse()
        return True

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
            return self.handle_help(nick, channel, output, topic="id")

        return True

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
            return self.handle_help(nick, channel, output, topic="key")

        return True

    @command_handler(r"^!lookup(\s(?P<rchan>\w+))?(\s(?P<mode>\w+))?"
        r"(\s(?P<text>.+))?")
    @command_handler(r"^!lu(?P<rchan>\w+)?(\s(?P<mode>\w+))?"
        r"(\s(?P<text>.+))?")
    def handle_lookup(self, nick, channel, output, rchan, mode, text):
        """Look up (search for) a song or album"""

        self.log.info("%s used !lookup" % nick)

        if not self.rwdb:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        rchan = rchan.lower()
        if rchan in self.channel_ids:
            cid = self.channel_ids.get(rchan)
        else:
            return self.handle_help(nick, channel, output, topic="lookup")
        rchn = self.channel_names[cid]

        if mode == "song":
            rows, unreported_results = self.rwdb.search_songs(cid, text)
            out = "%(rchan)s: %(album_name)s / %(song_title)s [%(song_id)s]"
        elif mode == "album":
            rows, unreported_results = self.rwdb.search_albums(cid, text)
            out = "%(rchan)s: %(album_name)s [%(album_id)s]"
        else:
            return self.handle_help(nick, channel, output, topic="lookup")

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

        return True

    @command_handler(r"^!lstats(\s(?P<rchan>\w+))?(\s(?P<days>\d+))?")
    def handle_lstats(self, nick, channel, output, rchan=None, days=30):
        """ Reports listener statistics, as numbers or a chart

        Arguments:
            rchan: channel to ask about, or maybe "chart"
            days: number of days to include data for chart"""

        self.log.info("%s used !lstats" % nick)

        if not self.rwdb:
            output.default.append("The Rainwave database is unavailable.")
            return True

        rs = []

        if rchan is not None:
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
            rs.append(self.shorten(url))
        else:
            return self.handle_help(nick, channel, output, topic="lstats")

        if channel == PRIVMSG:
            output.default.extend(rs)
            return True

        ltls = int(self.config.get("lasttime:lstats"))
        wls = int(self.config.get("wait:lstats"))
        if ltls < time.time() - wls:
            output.default.extend(rs)
            self.config.set("lasttime:lstats", time.time())
        else:
            output.privrs.extend(rs)
            wait = ltls + wls - int(time.time())
            output.privrs.append("I am cooling down. You cannot use !lstats in "
                "%s for another %s seconds." % (channel, wait))

        return True

    @command_handler(r"!newmusic(\s(?P<rchan>\w+))?")
    def handle_newmusic(self, nick, channel, output, rchan=None, force=True):
        """Check for new music and announce up to three new songs per station"""

        r = "Looking for new music on channel %s" % rchan
        r += ", force is %s" % force
        self.log.info(r)

        priv = self.config.get("privlevel:%s" % nick)
        if priv < 1:
            self.log.warning("%s does not have privs to use !newmusic" % nick)
            return True

        self.config.set("lasttime:musiccheck", time.time())

        if rchan is not None:
            rchan = rchan.lower()

        if rchan in self.channel_ids:
            cid = self.channel_ids[rchan]
        else:
            return self.handle_help(nick, channel, output, topic="newmusic")

        rchn = self.channel_names[cid]
        self.log.info("Looking for new music on the %s" % rchn)

        if force:
            self.config.set("maxid:%s" % cid, 0)

        maxid = self.config.get("maxid:%s" % cid)
        self.log.info("Looking for music newer than %s" % maxid)

        if self.rwdb:
            newmaxid = self.rwdb.get_max_song_id(cid)
        else:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        if newmaxid > int(maxid):
            songs = self.rwdb.get_new_song_info(cid)
            for r, url in songs:
                msg = "New on the %s: %s" % (rchn, r)
                if "http" in url:
                    msg += " <%s>" % self.shorten(url)
                output.rs.append(msg)
            self.config.set("maxid:%s" % cid, newmaxid)

        return True

    @command_handler(r"!nowplaying\s(?P<rchan>\w+)")
    @command_handler(r"!np(?P<rchan>\w+)")
    def handle_nowplaying(self, nick, channel, output, rchan=None):
        """Report what is currently playing on the radio"""

        self.log.info("%s used !nowplaying" % nick)

        rs = []

        if rchan is not None:
            rchan = rchan.lower()

        if rchan in self.channel_ids:
            cid = self.channel_ids[rchan]
        else:
            return self.handle_help(nick, channel, output, topic="nowplaying")
        rchn = self.channel_names[cid]

        url = "http://rainwave.cc/async/%s/get" % cid
        data = self.api_call(url)
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
            r = "Now playing on the %s: %s / %s by %s" % (rchn, album, song,
                artt)
            url = np["song_url"]
            if url and "http" in url:
                r += " <%s>" % self.shorten(url)

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
            return True

        if sched_id == int(self.config.get("np:%s" % cid)):
            output.privrs.extend(rs)
            r = "I am cooling down. You can only use !nowplaying in "
            r += "%s once per song." % channel
            output.privrs.append(r)
        else:
            output.default.extend(rs)
            self.config.set("np:%s" % cid, sched_id)

        return True

    @command_handler(r"!prevplayed(\s(?P<rchan>\w+))?(\s(?P<index>\d))?")
    @command_handler(r"!pp(?P<rchan>\w+)(\s(?P<index>\d))?")
    def handle_prevplayed(self, nick, channel, output, rchan=None, index=0):
        """Report what was previously playing on the radio

        Arguments:
            station: station to check
            index: (int) (0, 1, 2) which previously played song, higher number =
                further in the past"""

        self.log.info("%s used !prevplayed" % nick)

        rs = []

        if rchan is not None:
            rchan = rchan.lower()

        if rchan in self.channel_ids:
            cid = self.channel_ids.get(rchan)
        else:
            return self.handle_help(nick, channel, output, topic="prevplayed")
        rchn = self.channel_names[cid]

        try:
            index = int(index)
        except TypeError:
            index = 0
        if index not in [0, 1, 2]:
            return self.handle_help(nick, channel, output, topic="prevplayed")

        url = "http://rainwave.cc/async/%s/get" % cid
        data = self.api_call(url)
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
            r = "Previously on the %s: %s / %s by %s" % (rchn, album, song,
                artt)

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
            return True

        if sched_id == int(self.config.get("pp:%s:%s" % (cid, index))):
            output.privrs.extend(rs)
            r = "I am cooling down. You can only use !prevplayed in "
            r += "%s once per song." % channel
            output.privrs.append(r)
        else:
            output.default.extend(rs)
            self.config.set("pp:%s:%s" % (cid, index), sched_id)

        return True

    @command_handler(r"^!rate(\s(?P<rchan>\w+))?(\s(?P<rating>\w+))?")
    @command_handler(r"^!rt(?P<rchan>\w+)?(\s(?P<rating>\w+))?")
    def handle_rate(self, nick, channel, output, rchan=None, rating=None):
        """Rate the currently playing song

        Arguments:
            station: station of song to rate
            rating: the rating"""

        self.log.info("%s used !rate" % nick)

        if rchan is not None:
            rchan = rchan.lower()

        if rchan in self.channel_ids and rating:
            cid = self.channel_ids.get(rchan)
        else:
            return self.handle_help(nick, channel, output, topic="rate")

        # Make sure this nick matches a username

        user_id = self.config.get_id_for_nick(nick)

        if not user_id and self.rwdb:
            user_id = self.rwdb.get_id_for_nick(nick)

        if not user_id:
            r = "I do not have a user id stored for you. Visit "
            r += "http://rainwave.cc/auth/ to look up your user id and tell me "
            r += "about it with \x02!id add <id>\x02"
            output.privrs.append(r)
            return True

        # Get the key for this user

        key = self.config.get_key_for_nick(nick)
        if not key:
            r = "I do not have a key stored for you. Visit "
            r += "http://rainwave.cc/auth/ to get a key and tell me about it "
            r += "with \x02!key add <key>\x02"
            output.privrs.append(r)
            return True

        # Get the song_id

        url = "http://rainwave.cc/async/%s/get" % cid
        data = self.api_call(url)
        song_id = data["sched_current"]["song_data"][0]["song_id"]

        # Try the rate

        url = "http://rainwave.cc/async/%s/rate" % cid
        args = {"user_id": user_id, "key": key, "song_id": song_id,
            "rating": rating}
        data = self.api_call(url, args)

        if data["rate_result"]:
            output.privrs.append(data["rate_result"]["text"])
        else:
            output.privrs.append(data["error"]["text"])

        return True

    @command_handler(r"^!refresh(\s(?P<rchan>\w+))?")
    def handle_refresh(self, nick, channel, output, rchan=None):
        """See the status of or initiate a playlist refresh"""

        self.log.info("%s used !refresh" % nick)

        # This command requires privlevel 1

        priv = self.config.get("privlevel:%s" % nick)
        if priv < 1:
            self.log.warning("%s does not have privs to use !refresh" % nick)
            return True

        # This command requires the Rainwave database

        if self.rwdb is None:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        if rchan is not None:
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

        return True

    @command_handler(r"^!request(\s(?P<rchan>\w+))?(\s(?P<songid>\d+))?")
    @command_handler(r"^!rq(?P<rchan>\w+)?(\s(?P<songid>\d+))?")
    def handle_request(self, nick, channel, output, rchan=None, songid=None):
        """Request a song on the radio

        Arguments:
            station: the station to request on
            songid: id of song to request"""

        self.log.info("%s used !request" % nick)

        if rchan is not None:
            rchan = rchan.lower()

        if rchan in self.channel_ids and songid:
            cid = self.channel_ids.get(rchan)
        else:
            return self.handle_help(nick, channel, output, topic="request")

        user_id = self.config.get_id_for_nick(nick)

        if not user_id and self.rwdb:
            user_id = self.rwdb.get_id_for_nick(nick)

        if not user_id:
            r = "I do not have a user id stored for you. Visit "
            r += "http://rainwave.cc/auth/ to look up your user id and tell me "
            r += "about it with \x02!id add <id>\x02"
            output.privrs.append(r)
            return True

        key = self.config.get_key_for_nick(nick)
        if not key:
            r = "I do not have a key stored for you. Visit "
            r += "http://rainwave.cc/auth/ to get a key and tell me about it "
            r += "with \x02!key add <key>\x02"
            output.privrs.append(r)
            return True

        url = "http://rainwave.cc/async/%s/request" % cid
        args = {"user_id": user_id, "key": key, "song_id": songid}
        data = self.api_call(url, args)

        if data["request_result"]:
            output.privrs.append(data["request_result"]["text"])
        else:
            output.privrs.append(data["error"]["text"])

        return True

    @command_handler("!restart")
    def handle_restart(self, nick, channel, output):
        """Restart the bot"""

        self.log.info("%s used !restart" % nick)

        priv = int(self.config.get("privlevel:%s" % nick))
        if priv > 1:
            self.config.set("restart_on_stop", 1)
            self.handle_stop(nick, channel, output)
        else:
            self.log.warning("%s does not have privs to use !restart" % nick)

        return True

    @command_handler("!roll(\s(?P<dice>\d+)(d(?P<sides>\d+))?)?")
    def handle_roll(self, nick, channel, output, dice=None, sides=None):
        """Roll some dice"""

        self.log.info("%s used !roll" % nick)

        try:
            dice = min(int(dice), 100)
        except TypeError:
            dice = 1

        try:
            sides = min(int(sides), 100)
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
            return True

        ltr = int(self.config.get("lasttime:roll"))
        wr = int(self.config.get("wait:roll"))
        if ltr < time.time() - wr:
            output.default.append(r)
            self.config.set("lasttime:roll", time.time())
        else:
            output.privrs.append(r)
            wait = ltr + wr - int(time.time())
            r = "I am cooling down. You cannot use !roll in "
            r += "%s for another %s seconds." % (channel, wait)
            output.privrs.append(r)

        return True

    @command_handler(r"!(?P<mode>rock|paper|scissors)")
    def handle_rps(self, nick, channel, output, mode=None):
        """Rock, paper, scissors"""

        self.log.info("%s used !%s" % (nick, mode))

        rps = ["rock", "paper", "scissors"]
        challenge  = rps.index(mode)
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
        r += " Your current record is %s-%s-%s (w-d-l)." % (w, d, l)

        if channel == PRIVMSG:
            output.default.append(r)
            return True

        ltr = int(self.config.get("lasttime:rps"))
        wr = int(self.config.get("wait:rps"))
        if ltr < time.time() - wr:
            output.default.append(r)
            self.config.set("lasttime:rps", time.time())
        else:
            output.privrs.append(r)
            wait = ltr + wr - int(time.time())
            r = "I am cooling down. You cannot use !%s in %s " % (mode, channel)
            r += "for another %s seconds." % wait
            output.privrs.append(r)

        return True

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
            return True

        ltr = int(self.config.get("lasttime:rps"))
        wr = int(self.config.get("wait:rps"))
        if ltr < time.time() - wr:
            output.default.append(r)
            self.config.set("lasttime:rps", time.time())
        else:
            output.privrs.append(r)
            wait = ltr + wr - int(time.time())
            output.privrs.append("I am cooling down. You cannot use !rps in %s "
                "for another %s seconds." % (channel, wait))

        return True

    @command_handler(r"!rps rename(\s(?P<old>\S+))?(\s(?P<new>\S+))?")
    def handle_rps_rename(self, nick, channel, output, old=None, new=None):
        """Rename an RPS nick, useful for merging game histories"""

        self.log.info("%s used !rps rename" % nick)

        if self.config.get("privlevel:%s" % nick) > 1 and old and new:
            self.config.rename_rps_player(old, new)
            r = "I assigned the RPS game history for %s to %s." % (old, new)
            output.privrs.append(r)

        return True

    @command_handler(r"^!rps reset")
    def handle_rps_reset(self, nick, channel, output):
        """Reset RPS stats and delete game history for a nick"""

        self.log.info("%s used !rps reset" % nick)

        self.config.reset_rps_record(nick)
        r = "I reset your RPS record and deleted your game history."
        output.privrs.append(r)
        return True

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
            return True

        ltr = int(self.config.get("lasttime:rps"))
        wr = int(self.config.get("wait:rps"))
        if ltr < time.time() - wr:
            output.default.append(r)
            self.config.set("lasttime:rps", time.time())
        else:
            output.privrs.append(r)
            wait = ltr + wr - int(time.time())
            output.privrs.append("I am cooling down. You cannot use !rps in %s "
                "for another %s seconds." % (channel, wait))

        return True

    @command_handler(r"^!rps who")
    def handle_rps_who(self, nick, channel, output):
        """List all players in the RPS game history"""

        self.log.info("%s used !rps who" % nick)

        rs = []
        players = self.config.get_rps_players()

        mlnl = int(self.config.get("maxlength:nicklist"))
        while len(players) > mlnl:
            plist = players[:mlnl]
            players[:mlnl] = []
            r = "RPS players: " + ", ".join(plist)
            rs.append(r)
        r = "RPS players: " + ", ".join(players)
        rs.append(r)

        if channel == PRIVMSG:
            output.default.extend(rs)
            return True

        ltr = int(self.config.get("lasttime:rps"))
        wr = int(self.config.get("wait:rps"))
        if ltr < time.time() - wr:
            output.default.extend(rs)
            self.config.set("lasttime:rps", time.time())
        else:
            output.privrs.extend(rs)
            wait = ltr + wr - int(time.time())
            output.privrs.append("I am cooling down. You cannot use !rps in %s "
                "for another %s seconds." % (channel, wait))

        return True

    @command_handler(r"!stats(\s(?P<rchan>\w+))?")
    def handle_stats(self, nick, channel, output, rchan=None):
        """Report radio statistics"""

        self.log.info("%s used !stats" % nick)

        if rchan is not None:
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
            return True

        lts = int(self.config.get("lasttime:stats"))
        ws = int(self.config.get("wait:stats"))
        if lts < time.time() - ws:
            output.default.append(r)
            self.config.set("lasttime:stats", time.time())
        else:
            output.privrs.append(r)
            wait = lts + ws - int(time.time())
            output.privrs.append("I am cooling down. You cannot use !stats in "
                "%s for another %s seconds." % (channel, wait))

        return True

    @command_handler("!stop")
    def handle_stop(self, nick, channel, output):
        """Shut down the bot"""

        self.log.info("%s used !stop" % nick)

        priv = int(self.config.get("privlevel:%s" % nick))
        if priv > 1:
            self.config.set("who_stopped_me", nick)
            restart = int(self.config.get("restart_on_stop"))
            self.config.set("restart_on_stop", 0)
            if restart == 1:
                pid = subprocess.Popen([_abspath, "5"], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, stdin=subprocess.PIPE)
            # self.timer.cancel()
            self.die(self.config.get("msg:quit"))
        else:
            self.log.warning("%s does not have privs to use !stop" % nick)

        return True

    @command_handler(r"!unrated(\s(?P<rchan>\w+))?(\s(?P<num>\d+))?")
    def handle_unrated(self, nick, channel, output, rchan=None, num=None):
        """Report unrated songs"""

        self.log.info("%s used !unrated" % nick)

        if rchan is not None:
            rchan = rchan.lower()

        if rchan in self.channel_ids:
            cid = self.channel_ids.get(rchan)
        else:
            return self.handle_help(nick, channel, output, topic="unrated")

        try:
            num = int(num)
        except TypeError, ValueError:
            num = 1

        user_id = self.config.get_id_for_nick(nick)
        if not user_id and self.rwdb:
            user_id = self.rwdb.get_id_for_nick(nick)

        if not user_id:
            output.privrs.append("I do not have a user id stored for you. "
                "Visit http://rainwave.cc/auth/ to look up your user id and "
                "tell me about it with \x02!id add <id>\x02")
            return True

        if not self.rwdb:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        unrated = self.rwdb.get_unrated_songs(user_id, cid, num)
        for ucid, text in unrated:
            uchn = self.channel_names[ucid]
            output.privrs.append("%s: %s" % (uchn, text))

        return True

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
            output.default.append("I do not recognize the username '%s'." %
                target)
            return True

        uid = self.config.get("api:user_id")
        key = self.config.get("api:key")
        url = "http://rainwave.cc/async/1/listener_detail"
        args = {"user_id": uid, "key": key, "listener_uid": luid}
        data = self.api_call(url, args)

        if data["listener_detail"]:
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
            if cur_cid is not None:
                rch = self.channel_names[cur_cid]
                r = "%s is currently listening to the %s." % (cun, rch)
                rs.append(r)
        else:
            rs.append(data["error"]["text"])

        if channel == PRIVMSG:
            output.default.extend(rs)
            return True

        ltu = int(self.config.get("lasttime:ustats"))
        wu = int(self.config.get("wait:ustats"))
        if ltu < time.time() - wu:
            output.default.extend(rs)
            self.config.set("lasttime:ustats", time.time())
        else:
            output.privrs.extend(rs)
            wait = ltu + wu - int(time.time())
            output.privrs.append("I am cooling down. You cannot use !ustats in "
                "%s for another %s seconds." % (channel, wait))
        return True

    @command_handler(r"!vote(\s(?P<rchan>\w+))?(\s(?P<index>\d+))?")
    @command_handler(r"!vt(?P<rchan>\w+)?(\s(?P<index>\d+))?")
    def handle_vote(self, nick, channel, output, rchan=None, index=None):
        """Vote in the current election"""

        self.log.info("%s used !vote" % nick)

        if rchan is not None:
            rchan = rchan.lower()

        if rchan in self.channel_ids and index:
            cid = self.channel_ids.get(rchan)
        else:
            return self.handle_help(nick, channel, output, topic="vote")

        try:
            index = int(index)
        except TypeError, ValueError:
            return self.handle_help(nick, channel, output, topic="vote")

        if index not in [1, 2, 3]:
            return self.handle_help(nick, channel, output, topic="vote")

        user_id = self.config.get_id_for_nick(nick)

        if not user_id and self.rwdb:
            user_id = self.rwdb.get_id_for_nick(nick)

        if not user_id:
            output.privrs.append("I do not have a user id stored for you. "
                "Visit http://rainwave.cc/auth/ to look up your user id and "
                "tell me about it with \x02!id add <id>\x02")
            return True

        # Get the key for this user

        key = self.config.get_key_for_nick(nick)
        if not key:
            output.privrs.append("I do not have a key stored for you. Visit "
                "http://rainwave.cc/auth/ to get a key and tell me about it "
                "with \x02!key add <key>\x02")
            return True

        # Get the elec_entry_id

        url = "http://rainwave.cc/async/%s/get" % cid
        data = self.api_call(url)
        voteindex = index - 1
        song_data = data["sched_next"][0]["song_data"]
        elec_entry_id = song_data[voteindex]["elec_entry_id"]

        # Try the vote

        url = "http://rainwave.cc/async/%s/vote" % cid
        args = {"user_id": user_id, "key": key, "elec_entry_id": elec_entry_id}
        data = self.api_call(url, args)

        if data["vote_result"]:
            output.privrs.append(data["vote_result"]["text"])
        else:
            output.privrs.append(data["error"]["text"])

        return True

    @command_handler(r"!whois(\s(?P<target>.+))?")
    def handle_whois(self, nick, channel, output, target=None):
        """Do a whois"""

        self.log.info("!whois target: %s" % target)

        targets = []
        if target is not None:
            targets.append(target)

        self.connection.whois(targets)

        output.privrs.append("Check the log.")
        return True

    def on_307(self, c, e):
        """IRC event 307 is a response to a whois request where the target is a
        registered nick"""

        loginfo = {}
        loginfo["server"] = e.source()
        loginfo["nick"] = e.arguments()[0]
        self.log.info("%(server)s confirms that %(nick)s is a registered nick" %
            loginfo)

    def on_join(self, c, e):
        """This method is called when an IRC join event happens

        Arguments:
            c: the Connection object asociated with this event
            e: the Event object"""

        nick = e.source().split("!")[0]
        irc_chan = e.target()

        if nick == self.config.get("irc:nick"):
            # It's me!

            # If I recorded a ping timeout, tell everyone and clear it
            if int(self.config.get("ping_timeout")) == 1:
                r = ("I restarted because the IRC server hadn't pinged for %s "
                    "seconds." % self.config.get("timeout:ping"))
                self._to_irc(c, "privmsg", irc_chan, r)
                self.config.set("ping_timeout", 0)

            # If someone stopped me, call them out and clear it
            a = self.config.get("who_stopped_me")
            if a != 0:
                r = "I was stopped by %s." % a
                self._to_irc(c, "privmsg", irc_chan, r)
                self.config.set("who_stopped_me", 0)

        # Check for a join response
        jr = self.config.get("joinresponse:%s" % nick)
        if jr != -1:
            self._to_irc(c, "privmsg", irc_chan, jr)

        ja = self.config.get("joinaction:%s" % nick)
        if ja != -1:
            self._to_irc(c, "action", irc_chan, ja)

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
                if title is not None:
                    self.log.info("Found a title: %s" % title)
                    rs.append("[ %s ]" % title)

        # If there are no URLs, punt to the brain

        if len(rs) + len(privrs) == 0:
            talkrs = self._talk(msg)
            if len(talkrs) > 0:
                self.config.set("msg:last", msg)
                self.config.set("lasttime:msg", time.time())
                ltr = int(self.config.get("lasttime:respond"))
                wr = int(self.config.get("wait:respond"))

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

    def on_welcome(self, c, e):
        """This method is called when the bot first connects to the server

        Arguments:
            c: the Connection object associated with this event
            e: the Event object"""

        self.config.set("lasttime:ping", time.time())
        passwd = self.config.get("irc:nickservpass")
        self._to_irc(c, "privmsg", "nickserv", "identify %s" % passwd)
        c.join(self.config.get("irc:channel"))

    def api_call(self, url, args=None):
        """Make a call to the Rainwave API

        Arguments:
            url: the url of the API call
            args: a dictionary of optional arguments for the API call

        Returns: the API response object"""

        request = urllib2.Request(url)
        request.add_header("user-agent",
            "wormgas/0.1 +http://github.com/subtlecoolness/wormgas")
        request.add_header("accept-encoding", "gzip")
        if args:
            request.add_data(urllib.urlencode(args))
        opener = urllib2.build_opener()
        gzipdata = opener.open(request).read()
        gzipstream = StringIO.StringIO(gzipdata)
        result = gzip.GzipFile(fileobj=gzipstream).read()
        data = json.loads(result)
        return data

    def shorten(self, lurl):
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
        return result["id"]

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

        if title is not None:
            title = " ".join(title.split())
        return title

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

    def _periodic(self, c):
        # If I have not checked for forum activity for "timeout:forumcheck"
        # seconds, check now

        self.log.info("Performing periodic tasks")

        output = Output("public")

        ltfc = int(self.config.get("lasttime:forumcheck"))
        tofc = int(self.config.get("timeout:forumcheck"))
        if int(time.time()) > ltfc + tofc:
            self.log.info("Forum check timeout exceeded")
            nick = self.config.get("irc:nick")
            chan = self.config.get("irc:channel")
            self.handle_forum(nick, chan, output, force=False)

        ltmc = int(self.config.get("lasttime:musiccheck"))
        tomc = int(self.config.get("timeout:musiccheck"))
        if int(time.time()) > ltmc + tomc:
            self.log.info("Music check timeout exceeded")
            nick = self.config.get("irc:nick")
            chan = self.config.get("irc:channel")
            for rchan in self.channel_ids.keys():
                self.handle_newmusic(nick, chan, output, rchan=rchan,
                    force=False)

        for r in output.rs:
            self._to_irc(c, "privmsg", chan, r)

        # Come back in 60 seconds
        # self.timer = threading.Timer(60, self._periodic, [c])
        # self.timer.start()

    def _talk(self, msg=None):
        """Engage the brain, respond when appropriate

        Arguments:
            msg: the message to learn and possible reply to

        Returns: a list of strings"""

        # If I am not replying to anything in particular, use the last message
        if msg is None:
            msg = self.config.get("msg:last")

        # Ignore messages with certain words
        result = self.reignore.search(msg)
        if result is not None:
            return []

        # Clean up the message before sending to the brain
        tobrain = msg
        tobrain = tobrain.replace(self.config.get("irc:nick"), "")
        tobrain = tobrain.replace(":", "")

        self.brain.learn(tobrain)

        return [self.brain.reply(tobrain)]

def main():
    log = logging.getLogger("wormgas")
    log.setLevel(logging.DEBUG)
    _logpath = "%s/wormgas.log" % os.path.split(_abspath)[0]
    handler = logging.handlers.RotatingFileHandler(_logpath, maxBytes=20000000,
        backupCount=1)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - "
        "%(message)s"))
    logging.getLogger().addHandler(handler)

    bot = wormgas()
    bot.start()

if __name__ == "__main__":
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

    main()
