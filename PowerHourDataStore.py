import json
import os

class PowerHourDataStore:
	"""Persistent storage for Power Hour planning lists"""

	def __init__(self, path):
		self.path = path
		self.data = {}

		# If the backing file already exist, read data from it
		if os.path.exists(path):
			with open(self.path, 'r') as f:
				self.data = json.load(f)

	def __del__(self):
		self._flush()

	def _flush(self):
		"""Write data to file"""
		with open(self.path, 'w') as f:
			json.dump(self.data, f)

	def list(self, owner):
		"""Yield all items in an owner's list"""
		if owner in self.data:
			for item in self.data[owner]:
				yield item

	def add(self, owner, item):
		"""Add the item to the owner's list"""
		if owner not in self.data:
			self.data[owner] = []
		self.data[owner].append(item)
		self._flush()

	def remove(self, owner, item):
		"""Remove the item from the owner's list"""
		if owner in self.data:
			if item in self.data[owner]:
				self.data[owner].remove(item)
			if len(self.data[owner]) == 0:
				del self.data[owner]
			self._flush()

	def clear(self, owner):
		"""Remove all items from the owner's list"""
		if owner in self.data:
			del self.data[owner]
			self._flush()

	def up(self, owner, item):
		"""Move an item one step closer to the beginning of the list"""
		if owner in self.data:
			if item in self.data[owner]:
				orig_index = self.data[owner].index(item)
				if orig_index == 0:
					# Already at beginning of list
					return
				new_index = orig_index - 1
				self.data[owner].remove(item)
				self.data[owner].insert(new_index, item)
				self._flush()

	def down(self, owner, item):
		"""Move an item one step away from the beginning of the list"""
		if owner in self.data:
			if item in self.data[owner]:
				orig_index = self.data[owner].index(item)
				if orig_index + 1 == len(self.data[owner]):
					# Already at end of list
					return
				new_index = orig_index + 1
				self.data[owner].remove(item)
				self.data[owner].insert(new_index, item)
				self._flush()
