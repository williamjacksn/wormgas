#!/usr/bin/python
"""
wormgas -- IRC bot for Rainwave (http://rainwave.cc)
https://github.com/subtlecoolness/wormgas
"""

import gzip
import httplib
import json
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

import dbaccess
from ircbot import SingleServerIRCBot

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
        regex = re.compile(command)

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
            "You may rely on it."]


    station_names = ("Rainwave Network", "Game channel",  "OCR channel",
        "Covers channel", "Chiptune channel", "All channel")

    station_ids = {"game": 1, "ocr": 2, "cover": 3, "chip": 4, "all": 5}

    def __init__(self):
        (self.path, self.file) = os.path.split(_abspath)

        self.config = dbaccess.Config()
        self.config.open(self.path)

        try:
            self.rwdb = dbaccess.RainwaveDatabase(self.config)
            self.rwdb.connect()
        except dbaccess.RainwaveDatabaseUnavailableError:
            self.rwdb = None

        server = self.config.get("irc:server")
        nick = self.config.get("irc:nick")
        name = self.config.get("irc:name")
        SingleServerIRCBot.__init__(self, [(server, 6667)], nick, name)

    @command_handler("!8ball")
    def handle_8ball(self, nick, channel, output):
        """Ask a question of the magic 8ball."""
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
            cdmsg = ("I am cooling down. You cannot use !8ball in "
                    "%s for another %s seconds." % (channel, wait))
            output.privrs.append(cdmsg)
        return True

    @command_handler(r"^!config(\s(?P<id>[\w:]+))?(\s(?P<value>.+))?")
    def handle_config(self, nick, channel, output, id=None, value=None):
        """View and set config items"""

        priv = int(self.config.get("privlevel:%s" % nick))
        if priv > 1:
            output.privrs.extend(self.config.handle(id, value))
        return True

    @command_handler(r"!el(ection\s)?(?P<station>\w+)?(\s(?P<index>\d))?")
    def handle_election(self, nick, channel, output, station=None, index=None):
        """Show the candidates in an election"""

        # Make sure the index is valid.
        try:
            index = int(index)
        except TypeError:
            index = 0
        if index not in [0, 1]:
            # Not a valid index, return the help text.
            return(self.handle_help(nick, channel, output, topic="election"))

        if station in self.station_ids:
            sid = self.station_ids.get(station, 5)
        else:
            return(self.handle_help(nick, channel, output, topic="election"))

        sched_config = "el:%s:%s" % (sid, index)
        sched_id, text = self._fetch_election(index, sid)

        # Prepend the message description to the output string.
        time = ["Current", "Future"][index]
        result = "%s election on %s: %s" % (time, self.station_names[sid], text)

        if channel == PRIVMSG:
            output.privrs.append(result)
        elif sched_id == self.config.get(sched_config):
            # !election has already been called for this election
            output.privrs.append(result)
            output.privrs.append(
                    "I am cooling down. You can only use "
                    "!election in %s once per election." % channel)
        else:
            output.default.append(result)
            self.config.set(sched_config, sched_id)
        return True

    def _fetch_election(self, index, sid):
        """Return (sched_id, election string) for given index and sid.

        A sched_id is a unique ID given to every scheduled event, including
        elections. The results of this call can therefore be cached locally
        using the sched_id as the cache key.
        """

        data = self.api_call("http://rainwave.cc/async/%s/get" % sid)
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
            cdmsg = ("I am cooling down. You cannot use !flip in %s for "
                "another %s seconds." % (channel, wait))
            output.privrs.append(cdmsg)
        return True

    @command_handler(r"!forum")
    def handle_forum(self, nick, channel, output, force=True):
        """Check for new forum posts, excluding forums where the anonymous user
        has no access"""

        priv = self.config.get("privlevel:%s" % nick)
        if priv < 2:
            return True

        self.config.set("lasttime:forumcheck", time.time())

        if force:
            self.config.set("maxid:forum", 0)

        if self.rwdb:
            newmaxid = self.rwdb.get_max_forum_post_id()
        else:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        if newmaxid > int(self.config.get("maxid:forum")):
            r, url = self.rwdb.get_forum_post_info()
            surl = self.shorten(url)
            output.rs.append("New on the forums! %s <%s>" % (r, surl))

        return True

    @command_handler(r"^!help(\s(?P<topic>\w+))?")
    def handle_help(self, nick, channel, output, topic=None):
        """Look up help about a topic"""

        priv = self.config.get("privlevel:%s" % nick)
        rs = []

        stationcodes = ("Station codes are \x02" +
            "\x02, \x02".join(self.station_ids.keys()) + "\x02")

        if (topic is None) or (topic == "all"):
            rs.append("Use \x02!help [<topic>]\x02 with one of these topics: "
                "8ball, election, flip, id, key, lookup, lstats, nowplaying, "
                "prevplayed, rate, request, roll, rps, stats, unrated, ustats, "
                "vote")
            if priv > 0:
                rs.append("Level 1 administration topics: newmusic")
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
        elif topic == "election":
            rs.append("Use \x02!election <stationcode> [<index>]\x02 to see "
                "the candidates in an election")
            rs.append("Short version is \x02!el<stationcode> [<index>]\x02")
            rs.append("Index should be 0 (current) or 1 (future), default is 0")
            rs.append(stationcodes)
        elif topic == "flip":
            rs.append("Use \x02!flip\x02 to flip a coin")
        elif topic == "forum":
            if priv > 1:
                rs.append("Use \x02!forum\x02 to announce the most recent "
                    "forum post in the channel")
            else:
                rs.append("You are not permitted to use this command")
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
            rs.append("Use \x02!lookup <stationcode> song|album <text>\x02 "
                "to search for songs or albums with <text> in the title")
            rs.append("Short version is \x02!lu<stationcode> song|album "
                "<text>\x02")
            rs.append(stationcodes)
        elif topic == "lstats":
            rs.append("Use \x02!lstats [<stationcode>]\x02 to see information "
                "about current listeners, all stations are aggregated if you "
                "leave off <stationcode>")
            rs.append("Use \x02!lstats chart [<num>]\x02 to see a chart of "
                "average hourly listener activity over the last <num> days, "
                "leave off <num> to use the default of 30")
            rs.append(stationcodes)
        elif topic == "newmusic":
            if priv > 0:
                rs.append("Use \x02!newmusic <stationcode>\x02 to announce the "
                    "three most recently added songs on the station")
                rs.append(stationcodes)
            else:
                rs.append("You are not permitted to use this command")
        elif topic == "nowplaying":
            rs.append("Use \x02!nowplaying <stationcode>\x02 to show what is "
                "now playing on the radio")
            rs.append("Short version is \x02!np<stationcode>\x02")
            rs.append(stationcodes)
        elif topic == "prevplayed":
            rs.append("Use \x02!prevplayed <stationcode> [<index>]\x02 to show "
                "what was previously playing on the radio")
            rs.append("Short version is \x02!pp<stationcode> [<index>]\x02")
            rs.append("Index should be one of (0, 1, 2), 0 is default, higher "
                "numbers are further in the past")
            rs.append(stationcodes)
        elif topic == "rate":
            rs.append("Use \x02!rate <stationcode> <rating>\x02 to rate the "
                "currently playing song")
            rs.append("Short version is \x02!rt<stationcode> <rating>\x02")
            rs.append(stationcodes)
        elif topic == "request":
            rs.append("Use \x02!request <stationcode> <song_id>\x02 to add a "
                "song to your request queue, find the <song_id> using "
                "\x02!lookup\x02 or \x02!unrated\x02")
            rs.append("Short version is \x02!rq<stationcode> <song_id>\x02")
            rs.append(stationcodes)
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
            rs.append("Use \x02!stats [<stationcode>]\x02 to show information "
                "about the music collection, leave off <stationcode> to see "
                "the aggregate for all stations")
            rs.append(stationcodes)
        elif topic == "stop":
            if priv > 1:
                rs.append("Use \x02!stop\x02 to shut down the bot")
            else:
                rs.append("You are not permitted to use this command")
        elif topic == "unrated":
            rs.append("Use \x02!unrated <stationcode> [<num>]\x02 to see songs "
                "you have not rated, <num> can go up to 12, leave it off to "
                "see just one song")
            rs.append(stationcodes)
        elif topic == "ustats":
            rs.append("Use \x02!ustats [<nick>]\x02 to show user statistics "
                "for <nick>, leave off <nick> to see your own statistics")
        elif topic == "vote":
            rs.append("Use \x02!vote <stationcode> <index>\x02 to vote in the "
                "current election, find the <index> with \x02!election\x02")
            rs.append(stationcodes)
        else:
            rs.append("I cannot help you with '%s'" % topic)

        output.privrs.extend(rs)
        return True

    @command_handler(r"^!id(\s(?P<mode>\w+))?(\s(?P<id>\d+))?")
    def handle_id(self, nick, channel, output, mode=None, id=None):
        """Manage correlation between an IRC nick and Rainwave User ID

        Arguments:
            mode: string, one of "help", "add", "drop", "show"
            id: numeric, the person's Rainwave User ID"""

        # Make sure this nick is in the user_keys table
        self.config.store_nick(nick)

        if mode == "add" and id:
            self.config.add_id_to_nick(id, nick)
            output.privrs.append("I assigned the user id %s to nick '%s'" %
                (id, nick))
        elif mode == "drop":
            self.config.drop_id_for_nick(nick)
            output.privrs.append("I dropped the user id for nick '%s'" % nick)
        elif mode == "show":
            stored_id = self.config.get_id_for_nick(nick)
            if stored_id:
                output.privrs.append("The user id for nick '%s' is %s" %
                    (nick, stored_id))
            else:
                output.privrs.append("I do not have a user id for nick '%s'" %
                    nick)
        else:
            return(self.handle_help(nick, channel, output, topic="id"))

        return True

    @command_handler(r"^!key(\s(?P<mode>\w+))?(\s(?P<key>\w{10}))?")
    def handle_key(self, nick, channel, output, mode=None, key=None):
        """Manage API keys

        Arguments:
            mode: string, one of "help", "add", "drop", "show"
            key: string, the API key to add"""

        # Make sure this nick is in the user_keys table
        self.config.store_nick(nick)

        if mode == "add" and key:
            self.config.add_key_to_nick(key, nick)
            output.privrs.append("I assigned the API key '%s' to nick '%s'" %
                (key, nick))
        elif mode == "drop":
            self.config.drop_key_for_nick(nick)
            output.privrs.append("I dropped the API key for nick '%s'" % nick)
        elif mode == "show":
            stored_id = self.config.get_key_for_nick(nick)
            if stored_id:
                output.privrs.append("The API key for nick '%s' is '%s'" %
                    (nick, stored_id))
            else:
                output.privrs.append("I do not have an API key for nick '%s'" %
                    nick)
        else:
            return(self.handle_help(nick, channel, output, topic="key"))

        return True

    @command_handler(r"^!lookup(\s(?P<station>\w+))?(\s(?P<mode>\w+))?"
        r"(\s(?P<text>.+))?")
    @command_handler(r"^!lu(?P<station>\w+)?(\s(?P<mode>\w+))?"
        r"(\s(?P<text>.+))?")
    def handle_lookup(self, nick, channel, output, station, mode, text):
        """Look up (search for) a song or album"""

        if not self.rwdb:
            return ["Cannot access Rainwave database. Sorry."]

        if station in self.station_ids:
            sid = self.station_ids.get(station, 5)
        else:
            return(self.handle_help(nick, channel, output, topic="lookup"))
        st = self.station_names[sid]

        if mode == "song":
            rows, unreported_results = self.rwdb.search_songs(sid, text)
            out = "%(station)s: %(album_name)s / %(song_title)s [%(song_id)s]"
        elif mode == "album":
            rows, unreported_results = self.rwdb.search_albums(sid, text)
            out = "%(station)s: %(album_name)s [%(album_id)s]"
        else:
            return(self.handle_help(nick, channel, output, topic="lookup"))

        # If I got results, output them

        for row in rows:
            row["station"] = st
            output.privrs.append(out % row)

        # If I had to trim the results, be honest about it

        if unreported_results > 0:
            r = "%s: %s more result" % (st, unreported_results)
            if unreported_results > 1:
                r = "%ss" % r
            r = ("%s. If you do not see what you are looking for, be more "
                "specific with your search." % r)
            output.privrs.append(r)

        # If I did not find anything with this search, mention that

        if len(output.privrs) < 1:
            r = "%s: No results." % st
            output.privrs.append(r)
        elif unreported_results < 1:

            # I got between 1 and 10 results

            r = ("%s: Your search returned %s results." %
                (st, len(output.privrs)))
            output.privrs.insert(0, r)

        return True

    @command_handler(r"^!lstats(\s(?P<station>\w+))?(\s(?P<days>\d+))?")
    def handle_lstats(self, nick, channel, output, station=None, days=30):
        """ Reports listener statistics, as numbers or a chart

        Arguments:
            station: station to ask about, or maybe "chart"
            days: number of days to include data for chart"""

        if not self.rwdb:
            output.default.append("Cannot access Rainwave database. Sorry.")
            return True

        rs = []

        sid = self.station_ids.get(station, 0)
        st = self.station_names[sid]

        try:
            days = int(days)
        except TypeError:
            days = 30

        if station != "chart":
            regd, guest = self.rwdb.get_listener_stats(sid)
            rs.append("%s: %s registered users, %s guests." % (st, regd, guest))
        elif station == "chart":

            # Base url
            url = "http://chart.apis.google.com/chart"

            # Axis label styles
            url = "".join((url, "?chxs=0,676767,11.5,-1,l,676767"))

            # Visible axes
            url = "".join((url, "&chxt=y,x"))

            # Bar width and spacing
            url = "".join((url, "&chbh=a"))

            # Chart size
            url = "".join((url, "&chs=600x400"))

            # Chart type
            url = "".join((url, "&cht=bvs"))

            # Series colors
            c1 = "&chco=A2C180,3D7930,3399CC,244B95,FFCC33,"
            c2 = "FF9900,cc80ff,66407f,900000,480000"
            url = "".join((url, c1, c2))

            # Chart legend text
            t1 = "&chdl=Game+Guests|Game+Registered|OCR+Guests|"
            t2 = "OCR+Registered|Covers+Guests|Covers+Registered|"
            t3 = "Chiptune+Guests|Chiptune+Registered|All+Guests|"
            t4 = "All+Registered"
            url = "".join((url, t1, t2, t3, t4))

            # Chart title
            t1 = "&chtt=Rainwave+Average+Hourly+Usage+by+User+Type+and+Channel|"
            t2 = "%s+Day" % days
            if days > 1:
                t2 = "".join((t2, "s"))
            t3 = "+Ending+"
            t4 = time.strftime("%Y-%m-%d", time.gmtime())
            url = "".join((url, t1, t2, t3, t4))

            rwg = []
            rwr = []
            ocg = []
            ocr = []
            mwg = []
            mwr = []
            bwg = []
            bwr = []
            owg = []
            owr = []
            for sid, guests, users in self.rwdb.get_listener_chart_data(days):
                if sid == 1:
                    rwg.append(guests)
                    rwr.append(users)
                elif sid == 2:
                    ocg.append(guests)
                    ocr.append(users)
                elif sid == 3:
                    mwg.append(guests)
                    mwr.append(users)
                elif sid == 4:
                    bwg.append(guests)
                    bwr.append(users)
                elif sid == 5:
                    owg.append(guests)
                    owr.append(users)

            lmax = sum((max(rwg), max(rwr), max(ocg), max(ocr), max(mwg),
                max(mwr), max(bwg), max(bwr), max(owg), max(owr)))
            lceil = math.ceil(lmax / 50) * 50

            # Chart data
            url = "".join((url, "&chd=t:"))
            url = "".join((url, ",".join(["%s" % el for el in rwg]), "|"))
            url = "".join((url, ",".join(["%s" % el for el in rwr]), "|"))
            url = "".join((url, ",".join(["%s" % el for el in ocg]), "|"))
            url = "".join((url, ",".join(["%s" % el for el in ocr]), "|"))
            url = "".join((url, ",".join(["%s" % el for el in mwg]), "|"))
            url = "".join((url, ",".join(["%s" % el for el in mwr]), "|"))
            url = "".join((url, ",".join(["%s" % el for el in bwg]), "|"))
            url = "".join((url, ",".join(["%s" % el for el in bwr]), "|"))
            url = "".join((url, ",".join(["%s" % el for el in owg]), "|"))
            url = "".join((url, ",".join(["%s" % el for el in owr])))

            # Axis ranges
            t1 = "&chxr=0,0,%s|1,0,23" % lceil
            url = "".join((url, t1))

            # Scale for text format with custom range
            url = "".join((url, "&chds="))
            t1 = "0,%s" % lceil
            t2 = []
            for i in range(10):
                t2.append(t1)
            t3 = ",".join(t2)
            url = "".join((url, t3))
            rs.append(self.shorten(url))
        else:
            return(self.handle_help(nick, channel, output, topic="lstats"))

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

    @command_handler(r"!newmusic(\s(?P<station>\w+))?")
    def handle_newmusic(self, nick, channel, output, station=None, force=True):
        """Check for new music and announce up to three new songs per station"""

        priv = self.config.get("privlevel:%s" % nick)
        if priv < 1:
            return True

        if station in self.station_ids:
            sid = self.station_ids[station]
        else:
            return(self.handle_help(nick, channel, output, topic="newmusic"))

        if force:
            self.config.set("maxid:%s" % sid, 0)

        if self.rwdb:
            newmaxid = self.rwdb.get_max_song_id(sid)
        else:
            output.privrs.append("The Rainwave database is unavailable.")
            return True

        if newmaxid > int(self.config.get("maxid:%s" % sid)):
            songs = self.rwdb.get_new_song_info(sid)
            for r, url in songs:
                msg = "New on the %s: %s" % (self.station_names[sid], r)
                if "http" in url:
                    surl = self.shorten(url)
                    msg += " <%s>" % surl
                output.rs.append(msg)
            self.config.set("maxid:%s" % sid, newmaxid)

        return True

    @command_handler(r"!nowplaying\s(?P<station>\w+)")
    @command_handler(r"!np(?P<station>\w+)")
    def handle_nowplaying(self, nick, channel, output, station=None):
        """Report what is currently playing on the radio"""

        rs = []
        if station in self.station_ids:
            sid = self.station_ids[station]
        else:
            sid = 5
        st = self.station_names[sid]

        url = "http://rainwave.cc/async/%s/get" % sid
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
            r = "%s: Now playing: %s / %s by %s" % (st, album, song, artt)
            url = np["song_url"]
            if url and "http" in url:
                r = "%s <%s>" % (r, self.shorten(url))

            votes = np["elec_votes"]
            ratings = np["song_rating_count"]
            avg = np["song_rating_avg"]

            r = "%s (%s vote" % (r, votes)
            if votes <> 1:
                r = "%ss" % r
            r = "%s, %s rating" % (r, ratings)
            if ratings <> 1:
                r = "%ss" % r
            r = "%s, rated %s" % (r, avg)

            type = np["elec_isrequest"]
            if type in (3, 4):
                r = "%s, requested by %s" % (r, np["song_requestor"])
            elif type in (0, 1):
                r = "%s, conflict" % r
            r = "%s)" % r
            rs.append(r)
        else:
            r = "%s: I have no idea (sched_type = %s)" % (st, sched_type)
            rs.append(r)

        if channel == PRIVMSG:
            output.default.extend(rs)
            return True

        if sched_id == int(self.config.get("np:%s" % sid)):
            output.privrs.extend(rs)
            output.privrs.append("I am cooling down. You can only use "
                "!nowplaying in %s once per song." % channel)
        else:
            output.default.extend(rs)
            self.config.set("np:%s" % sid, sched_id)

        return True

    @command_handler(r"!prevplayed(\s(?P<station>\w+))?(\s(?P<index>\d))?")
    @command_handler(r"!pp(?P<station>\w+)(\s(?P<index>\d))?")
    def handle_prevplayed(self, nick, channel, output, station=None, index=0):
        """Report what was previously playing on the radio

        Arguments:
            station: station to check
            index: (int) (0, 1, 2) which previously played song, higher number =
                further in the past"""

        rs = []

        if station in self.station_ids:
            sid = self.station_ids.get(station)
        else:
            return(self.handle_help(nick, channel, output, topic="prevplayed"))
        st = self.station_names[sid]

        try:
            index = int(index)
        except TypeError:
            index = 0
        if index not in [0, 1, 2]:
            return(self.handle_help(nick, channel, output, topic="prevplayed"))

        url = "http://rainwave.cc/async/%s/get" % sid
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
            r = "%s: Previously: %s / %s by %s" % (st, album, song, artt)

            votes = pp["elec_votes"]
            avg = pp["song_rating_avg"]

            r = "%s (%s vote" % (r, votes)
            if votes <> 1:
                r = "%ss" % r
            r = "%s, rated %s" % (r, avg)

            type = pp["elec_isrequest"]
            if type in (3, 4):
                r = "%s, requested by %s" % (r, pp["song_requestor"])
            elif type in (0, 1):
                r = "%s, conflict" % r
            r = "%s)" % r
            rs.append(r)
        else:
            r = "%s: I have no idea (sched_type = %s)" % (st, sched_type)
            rs.append(r)

        if channel == PRIVMSG:
            output.default.extend(rs)
            return True

        if sched_id == int(self.config.get("pp:%s:%s" % (sid, index))):
            output.privrs.extend(rs)
            output.privrs.append("I am cooling down. You can only use "
                "!prevplayed in %s once per song." % channel)
        else:
            output.default.extend(rs)
            self.config.set("pp:%s:%s" % (sid, index), sched_id)

        return True

    @command_handler(r"^!rate(\s(?P<station>\w+))?(\s(?P<rating>\w+))?")
    @command_handler(r"^!rt(?P<station>\w+)?(\s(?P<rating>\w+))?")
    def handle_rate(self, nick, channel, output, station=None, rating=None):
        """Rate the currently playing song

        Arguments:
            station: station of song to rate
            rating: the rating"""

        if station in self.station_ids and rating:
            sid = self.station_ids.get(station)
        else:
            return(self.handle_help(nick, channel, output, topic="rate"))

        # Make sure this nick matches a username

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

        # Get the song_id

        url = "http://rainwave.cc/async/%s/get" % sid
        data = self.api_call(url)
        song_id = data["sched_current"]["song_data"][0]["song_id"]

        # Try the rate

        url = "http://rainwave.cc/async/%s/rate" % sid
        args = {"user_id": user_id, "key": key, "song_id": song_id,
            "rating": rating}
        data = self.api_call(url, args)

        if data["rate_result"]:
            output.privrs.append(data["rate_result"]["text"])
        else:
            output.privrs.append(data["error"]["text"])

        return True

    @command_handler(r"^!request(\s(?P<station>\w+))?(\s(?P<songid>\d+))?")
    @command_handler(r"^!rq(?P<station>\w+)?(\s(?P<songid>\d+))?")
    def handle_request(self, nick, channel, output, station=None, songid=None):
        """Request a song on the radio

        Arguments:
            station: the station to request on
            songid: id of song to request"""

        if station in self.station_ids and songid:
            sid = self.station_ids.get(station)
        else:
            return(self.handle_help(nick, channel, output, topic="request"))

        user_id = self.config.get_id_for_nick(nick)

        if not user_id and self.rwdb:
            user_id = self.rwdb.get_id_for_nick(nick)

        if not user_id:
            output.privrs.append("I do not have a user id stored for you. "
                "Visit http://rainwave.cc/auth/ to look up your user id and "
                "tell me about it with \x02!id add <id>\x02")
            return True

        key = self.config.get_key_for_nick(nick)
        if not key:
            output.privrs.append("I do not have a key stored for you. Visit "
                "http://rainwave.cc/auth/ to get a key and tell me about it "
                "with \x02!key add <key>\x02")
            return True

        url = "http://rainwave.cc/async/%s/request" % sid
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

        priv = int(self.config.get("privlevel:%s" % nick))
        if priv > 1:
            self.config.set("restart_on_stop", 1)
            self.handle_stop(nick, channel, output)

        return True

    @command_handler("!roll(\s(?P<dice>\d+)(d(?P<sides>\d+))?)?")
    def handle_roll(self, nick, channel, output, dice=None, sides=None):
        """Roll some dice"""

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
            output.privrs.append("I am cooling down. You cannot use !roll in "
                "%s for another %s seconds." % (channel, wait))

        return True

    @command_handler(r"!(?P<mode>rock|paper|scissors)")
    def handle_rps(self, nick, channel, output, mode=None):
        """Rock, paper, scissors"""

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
            output.privrs.append("I am cooling down. You cannot use !%s in %s "
                "for another %s seconds." % (mode, channel, wait))

        return True

    @command_handler(r"^!rps record(\s(?P<target>[\w!]+))?")
    def handle_rps_record(self, nick, channel, output, target=None):
        """Report RPS record for a nick"""

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

    @command_handler(r"!rps rename(\s(?P<old>\w+))?(\s(?P<new>\w+))?")
    def handle_rps_rename(self, nick, channel, output, old=None, new=None):
        """Rename an RPS nick, useful for merging game histories"""

        if self.config.get("privlevel:%s" % nick) > 1 and old and new:
            self.config.rename_rps_player(old, new)
            output.privrs.append("I assigned the RPS game history for %s to %s." %
                (old, new))

        return True

    @command_handler(r"^!rps reset")
    def handle_rps_reset(self, nick, channel, output):
        """Reset RPS stats and delete game history for a nick"""

        self.config.reset_rps_record(nick)
        output.privrs.append("I reset your RPS record and deleted your game "
            "history.")
        return True

    @command_handler(r"!rps stats(\s(?P<target>\w+))?")
    def handle_rps_stats(self, nick, channel, output, target=None):
        """Get some RPS statistics for a player"""

        if target is None:
            target = nick

        totals = self.config.get_rps_challenge_totals(target)
        games = sum(totals)
        if games > 0:
            r_rate = totals[0] / float(games) * 100
            p_rate = totals[1] / float(games) * 100
            s_rate = totals[2] / float(games) * 100

            #r = ("%s, %s, %s" % (totals[0], totals[1], totals[2]))
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

    @command_handler(r"!stats(\s(?P<station>\w+))?")
    def handle_stats(self, nick, channel, output, station=None):
        """Report radio statistics"""

        sid = self.station_ids.get(station, 0)
        if self.rwdb:
            songs, albums, hours = self.rwdb.get_radio_stats(sid)
            r = ("%s: %s songs in %s albums with %s hours of music." %
                (self.station_names[sid], songs, albums, hours))
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

        priv = int(self.config.get("privlevel:%s" % nick))
        if priv > 1:
            self.config.set("who_stopped_me", nick)
            restart = int(self.config.get("restart_on_stop"))
            self.config.set("restart_on_stop", 0)
            if restart == 1:
                pid = subprocess.Popen([_abspath, "5"], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, stdin=subprocess.PIPE)
            self.timer.cancel()
            self.die()

        return True

    @command_handler(r"!unrated(\s(?P<station>\w+))?(\s(?P<num>\d+))?")
    def handle_unrated(self, nick, channel, output, station=None, num=None):
        """Report unrated songs"""

        if station in self.station_ids:
            sid = self.station_ids.get(station)
        else:
            return(self.handle_help(nick, channel, output, topic="unrated"))

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

        unrated = self.rwdb.get_unrated_songs(user_id, sid, num)
        for usid, text in unrated:
            output.privrs.append("%s: %s" %
                (self.station_names[usid], text))

        return True

    @command_handler(r"!ustats(\s(?P<target>\w+))?")
    def handle_ustats(self, nick, channel, output, target=None):
        """Report user statistics"""

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

            # Line 1: winning/losing votes/requests

            r = "%s has %s winning vote" % (target, ld["radio_winningvotes"])
            if ld["radio_winningvotes"] != 1:
                r += "s"
            r += ", %s losing vote" % ld["radio_losingvotes"]
            if ld["radio_losingvotes"] != 1:
                r += "s"
            r += ", %s winning request" % ld["radio_winningrequests"]
            if ld["radio_winningrequests"] != 1:
                r += "s"
            r += ", %s losing request" % ld["radio_losingrequests"]
            if ld["radio_losingrequests"] != 1:
                r += "s"
            r += " (%s vote" % ld["radio_2wkvotes"]
            if ld["radio_2wkvotes"] != 1:
                r += "s"
            r += " in the last two weeks)."
            rs.append(r)

            # Line 2: rating progress

            game = ld["user_station_specific"]["1"]["rating_progress"]
            ocr = ld["user_station_specific"]["2"]["rating_progress"]
            cover = ld["user_station_specific"]["3"]["rating_progress"]
            chip = ld["user_station_specific"]["4"]["rating_progress"]
            r = ("%s has rated %d%% of Game, %d%% of OCR, %d%% of Covers, %d%% "
                "of Chiptune channel content." %
                (target, game, ocr, cover, chip))
            rs.append(r)

            # Line 3: What channel are you listening to?

            cur_chan = self.rwdb.get_current_channel(luid)
            if cur_chan is not None:
                r = ("%s is currently listening to the %s." %
                    (target, self.station_names[cur_chan]))
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

    @command_handler(r"!vote(\s(?P<station>\w+))?(\s(?P<index>\d+))?")
    @command_handler(r"!vt(?P<station>\w+)?(\s(?P<index>\d+))?")
    def handle_vote(self, nick, channel, output, station=None, index=None):
        """Vote in the current election"""

        if station in self.station_ids and index:
            sid = self.station_ids.get(station)
        else:
            return(self.handle_help(nick, channel, output, topic="vote"))

        try:
            index = int(index)
        except TypeError, ValueError:
            return(self.handle_help(nick, channel, output, topic="vote"))

        if index not in [1, 2, 3]:
            return(self.handle_help(nick, channel, output, topic="vote"))

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

        url = "http://rainwave.cc/async/%s/get" % sid
        data = self.api_call(url)
        voteindex = index - 1
        song_data = data["sched_next"][0]["song_data"]
        elec_entry_id = song_data[voteindex]["elec_entry_id"]

        # Try the vote

        url = "http://rainwave.cc/async/%s/vote" % sid
        args = {"user_id": user_id, "key": key, "elec_entry_id": elec_entry_id}
        data = self.api_call(url, args)

        if data["vote_result"]:
            output.privrs.append(data["vote_result"]["text"])
        else:
            output.privrs.append(data["error"]["text"])

        return True

    def on_join(self, c, e):
        """This method is called when an IRC join event happens

        Arguments:
            c: the Connection object asociated with this event
            e: the Event object"""

        nick = e.source().split("!")[0]

        if nick == self.config.get("irc:nick"):
            # It's me!

            # If I recorded a ping timeout, tell everyone and clear it
            if int(self.config.get("ping_timeout")) == 1:
                r = ("I restarted because the IRC server hadn't pinged for %s "
                "seconds." % self.config.get("timeout:ping"))
                c.privmsg(self.config.get("irc:channel"), r)
                self.config.set("ping_timeout", 0)

            # If someone stopped me, call them out and clear it
            a = self.config.get("who_stopped_me")
            if a != 0:
                r = "I was stopped by %s." % a
                c.privmsg(self.config.get("irc:channel"), r)
                self.config.set("who_stopped_me", 0)

        # Check for a join response
        jr = self.config.get("joinresponse:%s" % nick)
        if jr != -1:
            c.privmsg(self.config.get("irc:channel"), jr)

        # Start the periodic tasks.
        self._periodic(c)

    def on_ping(self, c, e):
        self.config.set("lasttime:ping", time.time())

    def on_privmsg(self, c, e):
        """This method is called when a message is sent directly to the bot

        Arguments:
            c: the Connection object associated with this event
            e: the Event object"""

        nick = e.source().split("!")[0]
        msg = e.arguments()[0].strip()

        rs = []
        privrs = []

        # Try all the command handlers

        output = Output("private")
        for command in _commands:
            if command(self, nick, msg, PRIVMSG, output):
                rs = output.rs
                privrs = output.privrs
                break

        # Send responses

        channel = self.config.get("irc:channel")
        for r in rs:
            if type(r) is unicode:
                message = r.encode("utf-8")
            else:
                message = unicode(r, "utf-8").encode("utf-8")
            c.privmsg(channel, message)

        for privr in privrs:
            if type(privr) is unicode:
                message = privr.encode("utf-8")
            else:
                message = unicode(privr, "utf-8").encode("utf-8")
            c.privmsg(nick, message)

    def on_pubmsg(self, c, e):
        """This method is called when a message is sent to the channel the bot
        is on

        Arguments:
            c: the Connection object associated with this event
            e: the Event object"""

        nick = e.source().split("!")[0]
        chan = e.target()
        msg = e.arguments()[0].strip()

        rs = []
        privrs = []

        # Try all the command handlers

        output = Output("public")
        for command in _commands:
            if command(self, nick, msg, chan, output):
                rs = output.rs
                privrs = output.privrs
                break

        # Send responses

        for r in rs:
            if type(r) is unicode:
                message = r.encode("utf-8")
            else:
                message = unicode(r, "utf-8").encode("utf-8")
            c.privmsg(chan, message)

        for privr in privrs:
            if type(privr) is unicode:
                message = privr.encode("utf-8")
            else:
                message = unicode(privr, "utf-8").encode("utf-8")
            c.privmsg(nick, message)

    def on_welcome(self, c, e):
        """This method is called when the bot first connects to the server

        Arguments:
            c: the Connection object associated with this event
            e: the Event object"""

        self.config.set("lasttime:ping", time.time())
        passwd = self.config.get("irc:nickservpass")
        c.privmsg("nickserv", "identify %s" % passwd)
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
        return(data)

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
        return(result["id"])

    def _periodic(self, c):
        # If I have not checked for forum activity for "timeout:forumcheck"
        # seconds, check now

        output = Output("public")

        ltfc = int(self.config.get("lasttime:forumcheck"))
        tofc = int(self.config.get("timeout:forumcheck"))
        if int(time.time()) > ltfc + tofc:
            nick = self.config.get("irc:nick")
            chan = self.config.get("irc:channel")
            self.handle_forum(nick, chan, output, force=False)

        for r in output.rs:
            if type(r) is unicode:
                message = r.encode("utf-8")
            else:
                message = unicode(r, "utf-8").encode("utf-8")
            c.privmsg(chan, message)

        # Come back in 60 seconds
        self.timer = threading.Timer(60, self._periodic, [c])
        self.timer.start()

def main():
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
