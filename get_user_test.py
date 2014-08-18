from mingl import *
import mingl

##AST validity tests

#test FriendOf
try:
    fr=FriendOf()
except Exception as e:
    assert str(e)=="at least 1 screen name must be specified to FriendOf","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"

try:
    fr=FriendOf(fr=FriendOf(1,2))
except Exception as e:
    assert str(e)=="arguments to FriendOf must be strings","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"
    
#test FollowerOf
try:
    fo=FriendOf()
except Exception as e:
    assert str(e)=="at least 1 screen name must be specified to FriendOf","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"

try:
    fo=FriendOf(fr=FriendOf(1,2))
except Exception as e:
    assert str(e)=="arguments to FriendOf must be strings","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"
    
#test Not
try:
    Not(1)
except Exception as e:
    assert str(e)=="Not can only contain FriendOf, FollowerOf, or Or clauses","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"
    
#test And
try:
    And()
except Exception as e:
    assert str(e)=="must supply at least 2 clauses to And","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"

try:
    And(1,"a")
except Exception as e:
    assert str(e)=="And clauses can only contain _QueryNodes","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"
 
try:
    And(And(FriendOf("a"),FriendOf("a")),FriendOf("a"))
except Exception as e:
    assert str(e)=="And clauses can not contain And clauses","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"

#test Or
try:
    Or()
except Exception as e:
    assert str(e)=="must supply at least 2 clauses to Or","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"

try:
    Or(And(FriendOf("a"),FriendOf("a")),FriendOf("a"))
except Exception as e:
    assert str(e)=="Or clauses can only contain FriendOf or FollowerOf clauses","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"
    
try:
    Or(FriendOf("a"),FollowerOf("a"))
except Exception as e:
    assert str(e)=="Or must contain clauses of the SAME type: either FriendOf or FollowerOf","wrong error: "+str(e)
else:
    assert False, "didn't receive expected exception"


##test _getFriendingUsers _getFollowedUsers _getNotFriendingUsers _getNotFollowedUsers
def sortedgroups(groups):
    return sorted([sorted(group) for group in groups])

#FriendFollower
fr=FriendOf("a","b")
assert sortedgroups(fr._getFriendingUsers())==[["a","b"]]
assert fr._getFollowedUsers()==[]
assert fr._getNotFriendingUsers()==[]
assert fr._getNotFollowedUsers()==[]

fo=FollowerOf("a","b")
assert sortedgroups(fo._getFollowedUsers())==[["a","b"]]
assert fo._getFriendingUsers()==[]
assert fo._getNotFriendingUsers()==[]
assert fo._getNotFollowedUsers()==[]

#Not
#TODO - uncomment this after suppor https://github.com/JnBrymn/minglbot/issues/26 works
# n = Not(FriendOf("a","b"))
# assert n._getFriendingUsers()==[]
# assert n._getFollowedUsers()==[]
# assert sortedgroups(n._getNotFriendingUsers())==[["a","b"]]
# assert n._getNotFollowedUsers()==[]

# n = Not(FollowerOf("a","b"))
# assert n._getFriendingUsers()==[]
# assert n._getFollowedUsers()==[]
# assert n._getNotFriendingUsers()==[]
# assert sortedgroups(n._getNotFollowedUsers())==[["a","b"]]

#Or
o=Or(FriendOf("a","b"),FriendOf("b","c"))
assert sortedgroups(o._getFriendingUsers())==[["a","b","c"]]
assert o._getFollowedUsers()==[]
assert o._getNotFriendingUsers()==[]
assert o._getNotFollowedUsers()==[]

o=Or(FollowerOf("a","b"),FollowerOf("b","c"))
assert sortedgroups(o._getFollowedUsers())==[["a","b","c"]]
assert o._getFriendingUsers()==[]
assert o._getNotFriendingUsers()==[]
assert o._getNotFollowedUsers()==[]

# #And

a=And(FriendOf("a","b"),FollowerOf("b","c"))
assert sortedgroups(a._getFriendingUsers())==[['a', 'b']]
assert sortedgroups(a._getFollowedUsers())==[['b','c']]
assert a._getNotFriendingUsers()==[]
assert a._getNotFollowedUsers()==[]

a=And(FriendOf("a","b"),Not(FollowerOf("b","c")),Not(FriendOf("c","d","e")))
assert sortedgroups(a._getFriendingUsers())==[['a', 'b']]
assert a._getFollowedUsers()==[]
assert sortedgroups(a._getNotFriendingUsers())==[['c','d','e']]
assert sortedgroups(a._getNotFollowedUsers())==[['b','c']]

#Complex
c=And(
    FriendOf("a","b"),
    Or(FollowerOf("c","e","d"),FollowerOf("f","e","g")),
    Not(Or(FriendOf("h","i"),FriendOf("j","i"))),
    Not(FriendOf("k","l"))
)
assert sortedgroups(c._getFriendingUsers())==[['a', 'b']]
assert sortedgroups(c._getFollowedUsers())==[["c","d","e","f","g"]]
assert sortedgroups(c._getNotFriendingUsers())==[['h','i','j'],['k','l']]
assert sortedgroups(c._getNotFollowedUsers())==[]

## test query building
import re
assert re.sub("\s+",
       " ",
       mingl._build_user_retrieval_query(friendingUsers=[['a','b'],['c','d']],followedUsers=[['f','g'],['h','i']]),
) == 'MATCH (x:User) WHERE x.screen_name IN ["a","b"] WITH collect(id(x)) AS fr0_id MATCH (x:User) WHERE x.screen_name IN ["c","d"] WITH fr0_id, collect(id(x)) AS fr1_id MATCH (x:User) WHERE x.screen_name IN ["f","g"] WITH fr0_id, fr1_id, collect(id(x)) AS fo0_id MATCH (x:User) WHERE x.screen_name IN ["h","i"] WITH fr0_id, fr1_id, fo0_id, collect(id(x)) AS fo1_id MATCH (fr0)-[:FOLLOWS]->(target), (fr1)-[:FOLLOWS]->(target), (target)-[:FOLLOWS]->(fo0), (target)-[:FOLLOWS]->(fo1) WHERE id(fr0) IN fr0_id AND id(fr1) IN fr1_id AND id(fo0) IN fo0_id AND id(fo1) IN fo1_id RETURN count(*) AS count, target ORDER BY count DESC LIMIT 1000;'
