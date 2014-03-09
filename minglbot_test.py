import minglbot
import os
from py2neo import neo4j

#Test setup
m = minglbot.MinglBot(os.getenv("TWITTER_CONSUMER_KEY"), os.getenv("TWITTER_CONSUMER_SECRET"))
kmbrymn = 134649059
jnbrymn = "jnbrymn"

def has_friend(minglbot,user_screen_name,friend_id):
    #TODO change to user,friend (can be id,screen_name,or user)
    result = neo4j.CypherQuery(minglbot.graph,"""
        MATCH (u:User{screen_name:LOWER({screen_name})})-[:FOLLOWS]->(f:User{id:{id}})
        RETURN COUNT(*)
    """).execute_one(screen_name=user_screen_name,id=friend_id)
    if result == 1:
        return True
    else:
        return False


#Test neo4j user CR_D #TODO add update
m._delete_user_from_neo4j("aaa")
u=m._get_user_from_neo4j("aaa")
assert u is None
m._create_user_in_neo4j("aaa")
u=m._get_user_from_neo4j("aaa")
assert u.screen_name == "aaa"
u=m._delete_user_from_neo4j(100)
u=m._get_user_from_neo4j(100)
assert u is None
m._create_user_in_neo4j(100)
u=m._get_user_from_neo4j(100)
assert u.id == 100
u=m._delete_user_from_neo4j(100)
u=m._get_user_from_neo4j(100)
assert u is None
u=m._delete_user_from_neo4j("aaa")
u=m._get_user_from_neo4j("aaa")
assert u is None


#Test basic hydration
m._delete_user_from_neo4j("jnbrymn")
u = m._hydrate_users_from_twitter(["jnbrymn"])
assert u[0]["name"] == "John Berryman"


#Test hydration with id screen_name conflict
m._delete_user_from_neo4j("jnbrymn")
m._create_user_in_neo4j(28881634) #jnbrymn's id
m._create_user_in_neo4j("jnbrymn")#there should now be two jnbrymn nodes one with id and one with screen_name
#hydrate users will reveal that jnbrymn is the same user as 17983820 and resolve the issue
#by combining nodes including all existing FOLLOWS relationships
us = m._hydrate_users_from_twitter(["jnbrymn","softwaredoug","patriciagorla","kmbrymn"])
assert us[0]["name"] == "John Berryman"
assert us[3]["name"] == "Kumiko Berryman"


#Test incremental hydration: e.g. if already hydrated in neo4j user that,
#but if present in neo4j and not hydrated OR if not present in neo4j, then
#get from Twitter
user1=1
user2=28881634
user3="kmbrymn"
m._delete_user_from_neo4j(user1)
m._delete_user_from_neo4j(user2)
m._delete_user_from_neo4j(user3)
neo4j.CypherQuery(m.graph,"""
    CREATE (u:User{id:{user1},screen_name:"blabla"})
    SET u.hydrated_at = 1234
""").run(user1=user1)
neo4j.CypherQuery(m.graph,"""
    CREATE (u:User{id:{user2}})
""").run(user2=user2)
us = m.hydrate_users([user1,user2,user3])
try:
    us[0]["name"] == None
except KeyError:
    assert "We expect a key error because the user was marked as hydrated even though it doesn't have a name"
assert us[1]["name"] == "John Berryman"
assert us[2]["name"] == "Kumiko Berryman"


#Test getting friends for jnbrymn and finding kmbrymn (id=134649059)
jnbrymn = "jnbrymn"
kmbrymn = 134649059
m._delete_user_from_neo4j(jnbrymn)
users = m._get_friends_from_twitter(jnbrymn) #should also connect the friends
assert has_friend(m,jnbrymn,kmbrymn)


#Test that get_friends doesn't go to twitter if user already hydrated
#but does if user is not hydrated or present in neo4j
user = "jnbrymn"
kmbrymn = 134649059
m._delete_user_from_neo4j(user)
neo4j.CypherQuery(m.graph,"""
    CREATE (u:User{screen_name:{user}})
    SET u.hydrated_at = 1234
""").run(user=user)
users = m.get_friends_for_user(user)
assert len(users) == 0
m._delete_user_from_neo4j(user)
users = m.get_friends_for_user(user)
assert has_friend(m,jnbrymn,kmbrymn)


#Test that get_mutual_friends returns friends
m._delete_user_from_neo4j(15547216)
m._delete_user_from_neo4j(628159493)
m._delete_user_from_neo4j("jnbrymn")
m._delete_user_from_neo4j("softwaredoug")
friends = m.get_mutual_friends([15547216,628159493,"jnbrymn","softwaredoug"],limit=100,min_num_mutual_friends=2)
assert len(friends[2]) > 0


#Test hydration of list of Users
m._delete_user_from_neo4j("jnbrymn")
u = minglbot.User("jnbrymn")
u.hydrated_at = 1 #cheating here by pretending that user is hydrated
users = m.hydrate_users(["jnbrymn",u])
assert len(users) == 1
assert users[0].id == None #since he doesn't have an id it proves that we haven't gone to Twitter



