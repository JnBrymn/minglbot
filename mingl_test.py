import mingl
import os
from py2neo import neo4j

######IMPORTANT FAST FAIL TEST##############
m = mingl.Mingl(os.getenv("TWITTER_CONSUMER_KEY"), os.getenv("TWITTER_CONSUMER_SECRET"), neo4j_host="localhost:7474")
test = neo4j.CypherQuery(m.graph,"""
    MATCH (x {this_is_a_test_db:true}) RETURN count(*)
""").execute_one()
if test != 1:
    raise Exception("TESTING ON NON-TEST GRAPH DB!!!!! ABORTED!!!!!\nCREATE ({this_is_a_test_db:true}) if this is a test db.")
######IMPORTANT FAST FAIL TEST##############

#Test setup
kmbrymn = 134649059
jnbrymn = "jnbrymn"

def _create_user_in_neo4j(mingl_bot,user):
    if type(user) is int:
        query = """
            MERGE (u:User {id:{id}})
            ON CREATE SET
                u.created_at = timestamp()
            RETURN u
        """
        u = neo4j.CypherQuery(mingl_bot.graph,query).execute_one(id=user)    
    elif type(user) is str:
        query = """
            MERGE (u:User {screen_name:LOWER({screen_name})})
            ON CREATE SET
                u.created_at = timestamp()
            RETURN u
        """
        u = neo4j.CypherQuery(mingl_bot.graph,query).execute_one(screen_name=user.lower())
    else:
        raise Exception("user must be either integer for id, string for screen_name")
    return mingl.User(u.get_properties())

        
def _delete_user_from_neo4j(mingl_bot,user):
    if type(user) is int:
        query = """
            MATCH (u:User {id:{id}})
            OPTIONAL MATCH (u)-[r]-()
            DELETE u,r
        """
        u = neo4j.CypherQuery(mingl_bot.graph,query).run(id=user)    
    elif type(user) is str:
        query = """
            MATCH (u:User {screen_name:LOWER({screen_name})})
            OPTIONAL MATCH (u)-[r]-()
            DELETE u,r
        """
        u = neo4j.CypherQuery(mingl_bot.graph,query).run(screen_name=user.lower())
    else:
        raise Exception("user must be either integer for id, string for screen_name")

def has_friend(mingl,user_screen_name,friend_id):
    #TODO change to user,friend (can be id,screen_name,or user)
    result = neo4j.CypherQuery(mingl.graph,"""
        MATCH (u:User{screen_name:LOWER({screen_name})})-[:FOLLOWS]->(f:User{id:{id}})
        RETURN COUNT(*)
    """).execute_one(screen_name=user_screen_name,id=friend_id)
    if result == 1:
        return True
    else:
        return False


#Test basic hydration
_delete_user_from_neo4j(m,"jnbrymn")
u = m._hydrate_users_from_twitter(["jnbrymn"])
assert u[0]["name"] == "John Berryman"


#Test hydration with id screen_name conflict
_delete_user_from_neo4j(m,"jnbrymn")
_create_user_in_neo4j(m,28881634) #jnbrymn's id
_create_user_in_neo4j(m,"jnbrymn")#there should now be two jnbrymn nodes one with id and one with screen_name
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
_delete_user_from_neo4j(m,user1)
_delete_user_from_neo4j(m,user2)
_delete_user_from_neo4j(m,user3)
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
_delete_user_from_neo4j(m,jnbrymn)
users = m._get_friends_from_twitter(jnbrymn) #should also connect the friends
assert has_friend(m,jnbrymn,kmbrymn)


#Test that get_mutual_friends returns friends
_delete_user_from_neo4j(m,15547216)
_delete_user_from_neo4j(m,628159493)
_delete_user_from_neo4j(m,"jnbrymn")
_delete_user_from_neo4j(m,"softwaredoug")
friends = m.get_mutual_friends([15547216,628159493,"jnbrymn","softwaredoug"],limit=100,min_num_mutual_friends=2)
assert len(friends[2]) > 0


#Test hydration of list of Users
_delete_user_from_neo4j(m,"jnbrymn")
u = mingl.User("jnbrymn")
u.hydrated_at = 1 #cheating here by pretending that user is hydrated
users = m.hydrate_users(["jnbrymn",u])
assert len(users) == 1
assert users[0].id == None #since he doesn't have an id it proves that we haven't gone to Twitter



#Test that get_mutual_friends takes and returns GroupedUsers
friends = {}
friends[3]=[15547216,628159493,"jnbrymn"]
friends[2]=["softwaredoug"]
groupedUsers = mingl.GroupedUsers(friends)
friends = m.get_mutual_friends(groupedUsers,limit=100,min_num_mutual_friends=2)
assert len(friends[2]) > 0
assert isinstance(friends,mingl.GroupedUsers)


