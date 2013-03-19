import requests

class RainwaveClientException(Exception):
	'''Raised for just about anything going wrong with RainwaveClient'''

class RainwaveClient(object):
	'''A RainwaveClient object provides a simple interface to the Rainwave API 
	(see http://rainwave.cc/api/ for details about the API)'''

	def __init__(self, base_url=None, user_id=None, key=None):

		# The Rainwave backend is open source, and it is possible this client would
		# like to talk to some other server besides http://rainwave.cc/
		self.base_url = u'http://rainwave.cc/' if base_url is None else base_url

		# There are some API endpoints that do not require authentication, so
		# user_id and key are optional
		self.user_id = user_id
		self.key = key
		self.req = requests.Session()

	def _call(self, path, args=dict()):
		'''Make a direct call to the API if you know the necessary path and
		arguments'''

		final_url = self.base_url + path.lstrip(u'/')

		if u'key' not in args and self.key is not None:
			args[u'key'] = self.key

		if u'user_id' not in args and self.user_id is not None:
			args[u'user_id'] = self.user_id

		if u'/get' in path:
			d = self.req.get(final_url)
		else:
			d = self.req.post(final_url, params=args)

		if d.ok:
			return d.json()
		else:
			d.raise_for_status()

	def add_one_time_play(self, channel_id, song_id, user_id=None, key=None):
		'''Add a one-time play to the schedule'''
		args = {u'song_id': song_id}
		if user_id is not None:
			args[u'user_id'] = user_id
		if key is not None:
			args[u'key'] = key
		return self._call(u'async/{}/oneshot_add'.format(channel_id), args)

	def channel_id_to_name(self, channel_id):
		'''Convert a channel id to a channel name'''
		channel_names = (u'Rainwave Network', u'Game channel', u'OCR channel',
			u'Covers channel', u'Chiptune channel', u'All channel')
		if channel_id < len(channel_names):
			return channel_names[channel_id]
		else:
			m = u'{} is not a valid channel id.'.format(channel_id)
			raise RainwaveClientException(m)

	def delete_one_time_play(self, channel_id, sched_id, user_id=None, key=None):
		'''Remove a one-time play from the schedule'''
		args = {u'sched_id': sched_id}
		if user_id is not None:
			args[u'user_id'] = user_id
		if key is not None:
			args[u'key'] = key
		return self._call(u'async/{}/oneshot_delete'.format(channel_id), args)

	def delete_request(self, requestq_id, user_id=None, key=None):
		args = {u'requestq_id': requestq_id}
		if user_id is not None:
			args[u'user_id'] = user_id
		if key is not None:
			args[u'key'] = key
		return self._call(u'async/1/request_delete', args)

	def get_all_albums(self, channel_id):
		'''Get a list of all albums, minimum information'''
		return self._call(u'async/{}/all_albums'.format(channel_id))

	def get_listener(self, listener_uid, user_id=None, key=None):
		'''Get details of a listener'''
		args = {u'listener_uid': listener_uid}
		if user_id is not None:
			args[u'user_id'] = user_id
		if key is not None:
			args[u'key'] = key
		return self._call(u'async/1/listener_detail', args)

	def get_requests(self, user_id=None, key=None):
		'''Get request queue for a user'''
		args = {}
		if user_id is not None:
			args[u'user_id'] = user_id
		if key is not None:
			args[u'key'] = key
		return self._call(u'async/1/requests_get', args)

	def get_timeline(self, channel_id):
		'''Get unauthenticated timeline'''
		return self._call(u'async/{}/get'.format(channel_id))

	def rate(self, channel_id, song_id, rating, user_id=None, key=None):
		'''Rate a song'''
		args = {u'song_id': song_id, u'rating': rating}
		if user_id is not None:
			args[u'user_id'] = user_id
		if key is not None:
			args[u'key'] = key
		return self._call(u'async/{}/rate'.format(channel_id), args)

	def request(self, channel_id, song_id, user_id=None, key=None):
		'''Add a song to the request queue'''
		args = {u'song_id': song_id}
		if user_id is not None:
			args[u'user_id'] = user_id
		if key is not None:
			args[u'key'] = key
		return self._call(u'async/{}/request'.format(channel_id), args)

	def vote(self, channel_id, elec_entry_id, user_id=None, key=None):
		'''Vote in an election'''
		args = {u'elec_entry_id': elec_entry_id}
		if user_id is not None:
			args[u'user_id'] = user_id
		if key is not None:
			args[u'key'] = key
		return self._call(u'async/{}/vote'.format(channel_id), args)
