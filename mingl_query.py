

# getUsers(["jnbrymn"])
# getUsers(FollowerOf("jnbrymn"))
# getUsers(FriendOf(["jnbrymn"]))
# getUsers(
#	And(
# 		FriendOf(["jnbrymn"]),
# 		FollowerOf("jnbrymn"),
#		Not(FollowerOf("patriciagorla"))
# 	)
# )
# getUsers can have a string screen name, an array (of screen names), or a queryNode


class queryNode(object):
	
	def __init__(self,*subnodes):
		self._subnodes=subnodes

	def _getFriendingUsers(self):
		friendingUsers = []
		for subNode in self._subnodes:
			subFriendingUsers = subNode._getFriendingUsers()
			if len(subFriendingUsers)>0:
				friendingUsers.append(subFriendingUsers)
		return friendingUsers

	def _getFollowedUsers(self):
		followedUsers = []
		for subNode in self._subnodes:
			subFollowedUsers = subNode._getFollowedUsers()
			if len(subFollowedUsers)>0:
				followedUsers.append(subFollowedUsers)
		return followedUsers
	

class And(queryNode):
	def __init__(self,*subnodes):
		for subnode in subnodes:
			if isinstance(subnode,And):
				raise Exception("Nested And clauses not supported for now.")
		super(And, self).__init__(*subnodes)


class FriendOf(queryNode):
	def __init__(self,*friendingUsers):
		for user in friendingUsers:
			if not isinstance(user,basestring):
				raise Exception("Arguments to FriendOf must be strings.")
		super(FriendOf, self).__init__()
		self._friendingUsers = friendingUsers

	def _getFriendingUsers(self):
		return self._friendingUsers

class FollowerOf(queryNode):
	def __init__(self,*followedUsers):
		for user in followedUsers:
			if not isinstance(user,basestring):
				raise Exception("Arguments to FollowerOf must be strings.")
		super(FollowerOf, self).__init__()
		self._followedUsers = followedUsers

	def _getFollowedUsers(self):
		return self._followedUsers

class Not(queryNode):
	def __init__(self,subnode):
		if not isinstance(subnode,(FriendOf,FollowerOf)):
			raise Exception("Not can only contain FriendOf or FollowerOf for now.")
		super(Not, self).__init__(subnode)

class AnyOf(queryNode):
	pass

