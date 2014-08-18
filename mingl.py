#TODOs
import os
import logging #see http://docs.python.org/2/howto/logging
logging.basicConfig(filename="mingl.log",level=logging.INFO)

class User(object):
    def __init__(self,user):
        self.id = None
        self.screen_name = None
        self.created_at = None
        self.hydrated_at = None
        self.friends_found_at = None
        self.followers_found_at = None
        self._properties = {}
        if isinstance(user,int):
            self.id = user
        elif isinstance(user,basestring):
            self.screen_name = user.lower()
        elif isinstance(user,dict):
            identified = False
            if "id" in user:
                self.id = user["id"]
                identified = True
            if "screen_name" in user:
                self.screen_name = user["screen_name"].lower()
                identified = True
            if not identified:
                err_msg = "all users must have either an id or a screen_name"
                logging.error(err_msg)
                raise Exception(err_msq)
            if "created_at" in user:
                self.created_at = user["created_at"]
            if "hydrated_at" in user:
                self.hydrated_at = user["hydrated_at"]
            if "friends_found_at" in user:
                self.friends_found_at = user["friends_found_at"]
            if "followers_found_at" in user:
                self.followers_found_at = user["followers_found_at"]
            self._properties = user
        elif isinstance(user,User):
            raise NotImplementedError()

    @property
    def identifier(self):
        if self.id:
            return id
        else:
            return screen_name

    def __getitem__(self,key):
        return self._properties[key]

    def __contains__(self,key):
        return key in self._properties

    def __repr__(self):
        return "User(id=%s,screen_name=%s)" % (str(self.id), self.screen_name)


from collections import OrderedDict
class GroupedUsers(OrderedDict):
    def __init__(self,d):
        for k,v in d.iteritems():
            if type(v) != list:
                raise Exception("All values in dict must be lists")

        super(GroupedUsers,self).__init__(reversed(sorted(d.items())))
        #after constructor runs make sure that no new users can be added
        self.__setattr__ = self._unimplemented

    def _unimplemented(self,key,val):
        raise Exception("not supported")

    def get_all(self):
        users = []
        for _,more_users in self.iteritems():
            users.extend(more_users)
        return users

    def get_all_with_min_popularity(self,n):
        """return list of users who have at least n followers from original group"""
        users = []
        for num,more_users in self.iteritems():
            if num >= n:
                users.extend(more_users)
        return users


from collections import defaultdict
import time
import tweepy
from py2neo import neo4j
import copy

class Mingl(object):
    @classmethod
    def _split_up_input(cls,input,types_map,error_on_unknown_type=True,num_to_use=float("inf")):
        if isinstance(input,GroupedUsers):
            input = input.get_all()
        elif not isinstance(input,list):
            input = [input]
        d = defaultdict(list)
        for i,el in enumerate(input):
            if i >= num_to_use:
                break
            for t,n in types_map.iteritems():
                if isinstance(el,t):
                    d[n].append(el)
                    break
            else:
                if error_on_unknown_type:
                    logging.error("unsupported %s" % type(el))
                    raise Exception("unsupported %s" % type(el))
        return d

    @classmethod
    def _twitter_exception_handling_runner(cls,func,**args):
        retrySeconds = 60*5
        while True:
            try:
                return func(**args)
            except tweepy.TweepError as e:
                if e.reason == "Not authorized.":
                    logging.info("Not authorized.") #TODO return errors when necessary
                    return [] #TODO is empty array the correct thing to return?
                elif e.reason == "Failed to send request: [Errno 50] Network is down":
                    logging.info("Network failure. Sleeping a bit and then retrying.")
                    time.sleep(retrySeconds)
                elif isinstance(e.message,list) and e[0][0]["code"] == 88:
                    logging.info("Rate limit exceeded. Sleeping")
                    time.sleep(retrySeconds)
                else:
                    logging.error("Unexpected error: %s",e.reason)
                    import pdb;pdb.set_trace()
                    raise e

    def __init__(self,
                 twitter_consumer_key,
                 twitter_consumer_secret,
                 twitter_bot_token=None,
                 twitter_bot_secret=None,
                 neo4j_host=None):
        logging.info("Initializing Mingl")
        twitter_bot_token = twitter_bot_token if twitter_bot_token else os.getenv("TWITTER_BOT_TOKEN")
        twitter_bot_secret = twitter_bot_secret if twitter_bot_secret else os.getenv("TWITTER_BOT_SECRET")
        auth = tweepy.OAuthHandler(twitter_consumer_key, twitter_consumer_secret)
        auth.set_access_token(twitter_bot_token, twitter_bot_secret)
        self.twitter = tweepy.API(auth)

        neo4j_host = neo4j_host if neo4j_host else os.getenv("NEO4J_HOST")
        self.graph = neo4j.GraphDatabaseService("http://"+ neo4j_host +"/db/data")

        #TODO move this to init script
        logging.info("Creating uniqueness constraint on User id and screen_name")
        try:
            neo4j.CypherQuery(graph,"""
                CREATE CONSTRAINT ON (u:User)
                ASSERT u.screen_name IS UNIQUE
            """).execute()
        except:
            pass

        try:
            neo4j.CypherQuery(graph,"""
                CREATE CONSTRAINT ON (u:User)
                ASSERT u.id IS UNIQUE
            """).execute()
        except:
            pass



    #Pulls up to 100 users from twitter by id or by screen_name.
    #If there is an id/screen_name conflict caused by two nodes representing the
    #same user, then this method will combine the two nodes including their FOLLOWs
    #relationships. Currently metadata can be lost such as the original created_at date
    def _hydrate_users_from_twitter(self,users):
        input = Mingl._split_up_input(users,{int:"ids",basestring:"screen_names"},num_to_use=float("inf"))
        ids = input["ids"]
        screen_names = input["screen_names"]
        if screen_names:
            screen_names = [screen_name.lower() for screen_name in screen_names]
        twitter_users = []
        if (ids and len(ids)>0) or (screen_names and len(screen_names)>0) :
            logging.info("Hydrating ids from Twitter. ids:(%s) screen_names:(%s) from Twitter",ids,screen_names)
            twitter_users = Mingl._twitter_exception_handling_runner(self.twitter.lookup_users, user_ids=ids, screen_names=screen_names)
        else:
            return []
        users = []
        for twitter_user in twitter_users:
            data = {'id': twitter_user.id,
                'name': twitter_user.name,
                'screen_name': twitter_user.screen_name.lower(),
                'description': twitter_user.description,
                'url': twitter_user.url,
                'followers_count': twitter_user.followers_count,
                'friends_count': twitter_user.friends_count,
                'listed_count': twitter_user.listed_count,
                'statuses_count': twitter_user.statuses_count,
                'favourites_count': twitter_user.favourites_count,
                'location': twitter_user.location,
                'time_zone': twitter_user.time_zone,
                'utc_offset': twitter_user.utc_offset,
                'lang': twitter_user.lang,
                'profile_image_url': twitter_user.profile_image_url,
                'geo_enabled': twitter_user.geo_enabled,
                'verified': twitter_user.verified,
                'notifications': twitter_user.notifications,
            }
            query_string = """
                MERGE (u:User {id:{id}}) 
                ON CREATE SET
                    u.created_at = timestamp()
                SET
                    u.name={name},
                    u.screen_name=LOWER({screen_name}),
                    u.description={description},
                    u.url={url},
                    u.followers_count={followers_count},
                    u.friends_count={friends_count},
                    u.listed_count={listed_count},
                    u.statuses_count={statuses_count},
                    u.favourites_count={favourites_count},
                    u.location={location},
                    u.time_zone={time_zone},
                    u.utc_offset={utc_offset},
                    u.lang={lang},
                    u.profile_image_url={profile_image_url},
                    u.geo_enabled={geo_enabled},
                    u.verified={verified},
                    u.notifications={notifications},
                    u.hydrated_at=timestamp()
                RETURN u
            """
            try:
                u = neo4j.CypherQuery(self.graph,query_string).execute_one(**data)
            except neo4j.CypherError:
                logging.info("Repairing id-screen_name conflict for id %d and screen_name %s",twitter_user.id,twitter_user.screen_name)
                neo4j.CypherQuery(self.graph,"""
                    MATCH (n:User{id:{id}}),(a:User{screen_name:LOWER({screen_name})})-[r:FOLLOWS]->(b)
                    CREATE UNIQUE (n)-[:FOLLOWS]->(b)
                    DELETE r
                """).run(id=twitter_user.id,screen_name=twitter_user.screen_name.lower())
                neo4j.CypherQuery(self.graph,"""
                    MATCH (n:User{id:{id}}),(a:User{screen_name:LOWER({screen_name})})<-[r:FOLLOWS]-(b)
                    CREATE UNIQUE (n)<-[:FOLLOWS]-(b)
                    DELETE r
                """).run(id=twitter_user.id,screen_name=twitter_user.screen_name.lower())
                neo4j.CypherQuery(self.graph,"""
                    MATCH (n:User{id:{id}}),(a:User{screen_name:LOWER({screen_name})})
                    DELETE a
                    SET n.screen_name=LOWER({screen_name})
                """).run(id=twitter_user.id,screen_name=twitter_user.screen_name.lower())
                u = neo4j.CypherQuery(self.graph,query_string).execute_one(**data)
            users.append(User(u.get_properties()))
        return users

    def hydrate_users(self,users,num_to_use=100):
        """Populates all parameters of supplied users.

        Attempts to hydrate users from neo4j. If user is not present or if hydrated_at
        is None then this method will hydrate the users from Twitter
        """
        input = Mingl._split_up_input(users,{int:"ids",basestring:"screen_names",User:"users"},num_to_use=num_to_use)
        ids = input["ids"]
        screen_names = input["screen_names"]
        users = input["users"]
        logging.info("Hydrating from neo4j. ids:(%s) screen_names:(%s) users:(%s)",ids,screen_names,users)
        if screen_names:
            screen_names = [screen_name.lower() for screen_name in screen_names]
        hydrated_users = []

        #pull out all users that are already hydrated
        if users:
            for user in users:
                if user.hydrated_at:
                    hydrated_users.append(user)
                    if user.id in ids: ids.remove(user.id)
                    if user.screen_name in screen_names: screen_names.remove(user.screen_name)
                elif user.id:
                    ids.append(user.id)
                else:
                    screen_names.append(user.screen_name)

        getUsersQuery = """
            MATCH (u:User)
            WHERE u.id IN {ids} 
             OR u.screen_name IN {screen_names}
            RETURN u
        """
        for u in neo4j.CypherQuery(self.graph,getUsersQuery).execute(ids=ids,screen_names=screen_names):
            user = u.values[0]
            id = user["id"]
            if user["screen_name"]:
                screen_name = user["screen_name"].lower()
            if user["hydrated_at"]:
                hydrated_users.append(User(user.get_properties()))
                if id in ids: ids.remove(id)
                if screen_name in screen_names: screen_names.remove(screen_name)

        unhydrated_users = []
        unhydrated_users.extend(ids)
        unhydrated_users.extend(screen_names)
        hydrated_users.extend(self._hydrate_users_from_twitter(unhydrated_users))

        return hydrated_users

    max_users_retrieved = 5000 #the current max retrieved by one request 
    def _get_relations_from_twitter(self,
            user,
            direction, #can be "friends" or "followers"
            count=max_users_retrieved, 
            return_users=True):
        logging.info("Getting {direction} of {user} from Twitter".format(direction=direction,user=user))
        
        if direction == "friends":
            arrow = "-[:FOLLOWS]->"
            method = self.twitter.friends_ids
        elif direction == "followers":
            arrow = "<-[:FOLLOWS]-"
            method = self.twitter.followers_ids
        else:
            raise Exception("direction must be one of \"friends\" or \"followers\"")
    
        ids = []
        query = ""
        cursor = -1
        if isinstance(user,int):
            while len(ids) < count:
                new_ids, cursors = Mingl._twitter_exception_handling_runner(method,user_id=user,cursor=cursor)
                ids.extend(new_ids)
                if cursors[1] == 0:
                    break
                else:
                    cursor = cursors[1]
            query += "MERGE (a:User {id:{id}})"
        elif isinstance(user,basestring):
            user = user.lower()
            while len(ids) < count:
                new_ids, cursors = Mingl._twitter_exception_handling_runner(method,screen_name=user,cursor=cursor)
                ids.extend(new_ids)
                if cursors[1] == 0:
                    break
                else:
                    cursor = cursors[1]
            query += "MERGE (a:User {screen_name:{screen_name}})"
        else:
            err_msg = "user must be either integer for id, string for screen_name. Found %s" % str(user)
            logging.error(err_msg)
            raise Exception(err_msg)
        query += """
            ON CREATE SET
              a.created_at = timestamp()
            SET a.{direction}_found_at = timestamp()
            FOREACH (id IN {{ids}} |
              MERGE (b:User {{id:id}})
              ON CREATE SET
                b.created_at = timestamp()
              CREATE UNIQUE (a){arrow}(b)
            )
        """.format(direction=direction,arrow=arrow)
        neo4j.CypherQuery(self.graph,query).run(id=user,screen_name=user,ids=ids)

        if return_users:
            users = []
            for id in ids:
                user = User(id)
                user.created_at = 1
                users.append(user)
            return users

    def _insert_into_graph_if_not_present(self,ids,screen_names,direction,count=max_users_retrieved):
        """Adds nodes for ids and screen_names if they aren't already present.

        Keyword arguments:
        ids -- twitter user id numbers
        screen_names -- twitter screen screen_names
        direction -- either "friends" or "followers"
        count -- the number of users to retrieve from twitter (default 5000)
        """

        if direction == "friends":
            arrow = "-[:FOLLOWS]->"
        elif direction == "followers":
            arrow = "<-[:FOLLOWS]-"
        else:
            raise Exception("direction must be one of \"friends\" or \"followers\"")

        logging.info("Getting {direction}. ids:({ids}) screen_names:({screen_names})".format(direction=direction,ids=ids,screen_names=screen_names))

        #First, get list of users for whom relations have not been retrieved
        if screen_names:
            screen_names = [screen_name.lower() for screen_name in screen_names]
        ids_copy = copy.copy(ids)
        screen_names_copy = copy.copy(screen_names)
        getUsersQuery = """
            MATCH (u:User)
            WHERE u.id in {ids} 
             OR u.screen_name in {screen_names}
            RETURN u
        """
        for u in neo4j.CypherQuery(self.graph,getUsersQuery).execute(ids=ids_copy,screen_names=screen_names_copy):
            user = u.values[0]
            if user[direction+"_found_at"]:
                if user["id"] and (user["id"] in ids_copy):
                    ids_copy.remove(user["id"])
                if user["screen_name"]:
                    screen_name = user["screen_name"].lower()
                    if screen_name in screen_names_copy: screen_names_copy.remove(screen_name)

        #Load missing users into neo4j from twitter
        ids_copy.extend(screen_names_copy)
        for id in ids_copy:
            self._get_relations_from_twitter(id, direction=direction, count=count, return_users=False)


    def get_relations(self,
            users,
            direction, #can be friends or followers
            num_to_use=float("inf"),
            limit=100,
            count_from_twitter=max_users_retrieved,
            min_num_mutual_relations=1
            ):
        """Retrieve relations. DEPRICATED

        Keyword arguments:
        num_to_use -- issues query based only upon the first num_to_use users (default inf)
        limit -- the number of relations to return (default 100)
        count_from_twitter -- for each user who's relations are retrieved, how many users to retrieve from twitter (default 5000)
        min_num_mutual_relations -- all users returned must be mutual relations of this number of input relations (default 1)
        """

        input = Mingl._split_up_input(users,{int:"ids",basestring:"screen_names",User:"users"},num_to_use=num_to_use)
        ids = input["ids"]
        screen_names = input["screen_names"]
        for the_user in input["users"]:
            if the_user.id:
                ids.append(the_user.id)
            else:
                screen_names.append(the_user.screen_name)

        if direction == "friends":
            arrow = "-[:FOLLOWS]->"
        elif direction == "followers":
            arrow = "<-[:FOLLOWS]-"
        else:
            raise Exception("direction must be one of \"friends\" or \"followers\"")

        self._insert_into_graph_if_not_present(ids,screen_names,direction,count_from_twitter)

        #Retrieve list of mutual relations sorted by number of mutual relationships
        query = """
            MATCH (u:User){arrow}(f:User)
            WHERE u.screen_name IN {{screen_names}}
               OR u.id IN {{ids}}
            WITH count(*) AS c,f
            ORDER BY c desc
            LIMIT {{limit}}
            WHERE c >= {{min_num_mutual_relations}}
            RETURN c, f
        """.format(arrow=arrow)
        results = neo4j.CypherQuery(self.graph,query).execute(
            ids=ids,
            screen_names=screen_names,
            limit=limit,
            min_num_mutual_relations=min_num_mutual_relations
        )
        relations = defaultdict(list)
        for r in results:
            relations[r.values[0]].append(User(r.values[1].get_properties()))
        return GroupedUsers(relations)

    def get_friends(self,
            users,
            num_to_use=float("inf"),
            limit=100,
            count_from_twitter=max_users_retrieved, 
            min_num_mutual_friends=1
            ):
        "depricated"
        return self.get_relations(users,"friends",num_to_use,limit,count_from_twitter,min_num_mutual_friends)


    def get_followers(self,
            users,
            num_to_use=float("inf"),
            limit=100,
            count_from_twitter=max_users_retrieved,
            min_num_mutual_followers=1
            ):
        "depricated"
        return self.get_relations(users,"followers",num_to_use,limit,count_from_twitter,min_num_mutual_followers)

#### NEW API BELOW 
    def get_users(self,
            where,
            count_from_twitter=max_users_retrieved
            ):
        if not isinstance(where,_QueryNode):
            raise "argument to get_users must be a _QueryNode specifying a query, or a string, or string array specifying screen_names"
        #todo add limit parameter
        #todo add possibility for just specifying a list of screen names
        #  just wrap the screen names in an Among clause and send that to getUsers again

        friendingUsers = where._getFriendingUsers()
        followedUsers = where._getFollowedUsers()

        #add users as necessary to the graph 
        def get_user_set(groups):
            allUsers = []
            [allUsers.extend(group) for group in groups]
            return list(set(allUsers))
        allFriendingUsers = get_user_set(friendingUsers)
        allFollowedUsers = get_user_set(followedUsers)
        self._insert_into_graph_if_not_present([],allFriendingUsers,"friends",count_from_twitter)
        self._insert_into_graph_if_not_present([],allFollowedUsers,"followers",count_from_twitter)

        #make query
        #TODO add to arguments count_from_twitter=max_users_retrieved, min_num_mutual_relations=1
        #     add to cypher query
        #       LIMIT {{limit}}
        #       WHERE c >= {{min_num_mutual_relations}}
        #       RETURN c, f
        query = _build_user_retrieval_query(friendingUsers=friendingUsers,followedUsers=followedUsers)
        results = neo4j.CypherQuery(self.graph,query).execute()
        relations = defaultdict(list)
        for r in results:
            relations[r.values[0]].append(User(r.values[1].get_properties()))
        relations = GroupedUsers(relations)

        #hydrate the users 
        #TODO this is riduculous sloppy code - fix it https://github.com/JnBrymn/minglbot/issues/32
        self.hydrate_users(relations)
        query = _build_user_retrieval_query(friendingUsers=friendingUsers,followedUsers=followedUsers)
        results = neo4j.CypherQuery(self.graph,query).execute()
        relations = defaultdict(list)
        for r in results:
            relations[r.values[0]].append(User(r.values[1].get_properties()))
        relations = GroupedUsers(relations)
        return relations



## QUERY NODES

class _QueryNode(object):
    def __init__(self,*subnodes):
        for subnode in subnodes:
            if not isinstance(subnode,_QueryNode):
                raise Exception("And clauses can only contain _QueryNodes")
        self._subnodes=subnodes

    #typically inheriting classes will override these methods, often with recursive calls to subnodes
    def _getFriendingUsers(self):
        return []
    def _getFollowedUsers(self):
        return []
    def _getNotFriendingUsers(self):
        return []
    def _getNotFollowedUsers(self):
        return []

class And(_QueryNode):
    def __init__(self,*subnodes):
        if len(subnodes) < 2:
            raise Exception("must supply at least 2 clauses to And")
        for subnode in subnodes:
            if isinstance(subnode,And):
                raise Exception("And clauses can not contain And clauses")
            elif not isinstance(subnode,_QueryNode):
                raise Exception("And clauses can only contain _QueryNodes")
        super(And, self).__init__(*subnodes)
        
    def _getFriendingUsers(self):
        friendingUsers = []
        for subNode in self._subnodes:
            subFriendingUsers = subNode._getFriendingUsers()
            if len(subFriendingUsers)>0:
                friendingUsers.extend(subFriendingUsers)
        return friendingUsers

    def _getFollowedUsers(self):
        followedUsers = []
        for subNode in self._subnodes:
            subFollowedUsers = subNode._getFollowedUsers()
            if len(subFollowedUsers)>0:
                followedUsers.extend(subFollowedUsers)
        return followedUsers
    
    def _getNotFriendingUsers(self):
        notFriendingUsers = []
        for subNode in self._subnodes:
            subNotFriendingUsers = subNode._getNotFriendingUsers()
            if len(subNotFriendingUsers)>0:
                notFriendingUsers.extend(subNotFriendingUsers)
        return notFriendingUsers

    def _getNotFollowedUsers(self):
        notFollowedUsers = []
        for subNode in self._subnodes:
            subNotFollowedUsers = subNode._getNotFollowedUsers()
            if len(subNotFollowedUsers)>0:
                notFollowedUsers.extend(subNotFollowedUsers)
        return notFollowedUsers

        
class Or(_QueryNode):
    def __init__(self,*subnodes):
        if len(subnodes) < 2:
            raise Exception("must supply at least 2 clauses to Or")
        kind = type(subnodes[0])
        for subnode in subnodes:
            if not isinstance(subnode,(FriendOf,FollowerOf)):
                raise Exception("Or clauses can only contain FriendOf or FollowerOf clauses")
            if not isinstance(subnode,kind):
                raise Exception("Or must contain clauses of the SAME type: either FriendOf or FollowerOf")
        super(Or, self).__init__(*subnodes)
    
    def _getFriendingUsers(self):
        friendingUsers = []
        for subnode in self._subnodes:
            subFriendingUsers = subnode._getFriendingUsers()
            if len(subFriendingUsers):
                friendingUsers.extend(subFriendingUsers[0])
        if len(friendingUsers) > 0:
            return [list(set(friendingUsers))]
        else:
            return []
    
    def _getFollowedUsers(self):
        followedUsers = []
        for subnode in self._subnodes:
            subFollowedUsers = subnode._getFollowedUsers()
            if len(subFollowedUsers):
                followedUsers.extend(subFollowedUsers[0])
        if len(followedUsers) > 0:
            return [list(set(followedUsers))]
        else:
            return []


class FriendOf(_QueryNode):
    def __init__(self,*friendingUsers):
        if len(friendingUsers) < 1:
            raise Exception("at least 1 screen name must be specified to FriendOf")
        for user in friendingUsers:
            if not isinstance(user,basestring):
                raise Exception("arguments to FriendOf must be strings")
        self._friendingUsers = list(friendingUsers)
        super(FriendOf, self).__init__()

    def _getFriendingUsers(self):
        return [list(set(self._friendingUsers))]
    
    
class FollowerOf(_QueryNode):
    def __init__(self,*followedUsers):
        if len(followedUsers) < 1:
            raise Exception("at least 1 screen name must be specified to FollowerOf")
        for user in followedUsers:
            if not isinstance(user,basestring):
                raise Exception("arguments to FollowerOf must be strings")
        self._followedUsers = list(followedUsers)
        super(FollowerOf, self).__init__()

    def _getFollowedUsers(self):
        return [list(set(self._followedUsers))]

class Not(_QueryNode):
    def __init__(self,subnode):
        print ("Not is implemented correctly but doesn't have support in the cypher creation of get_users\n"
               "see https://github.com/JnBrymn/minglbot/issues/26")
               
        if not isinstance(subnode,(FriendOf,FollowerOf,Or)):
            raise Exception("Not can only contain FriendOf, FollowerOf, or Or clauses")
        super(Not, self).__init__(subnode)
    def _getNotFriendingUsers(self):
        return self._subnodes[0]._getFriendingUsers()
    def _getNotFollowedUsers(self):
        return self._subnodes[0]._getFollowedUsers()

class Among(_QueryNode):
    def __init__(self,*users):
        raise Exception("not implemented")
        #Among can be used in Or
        #Among can be used in Not
        #_getAmongUsers and _getNotAmongUsers must be added
        #Only a single Among or NotAmong group can exist at the top level
        #The Among and NotAmong can be merged a shorter Among list
        

import re
screen_name_re = re.compile(r"^\w+$")
def _escape_user_list(users):
    return '["'+ '","'.join([user.lower() for user in users if screen_name_re.match(user)]) +'"]'
    
def _build_user_retrieval_query(friendingUsers=[],followedUsers=[]):
    
    #to keep me from fat fingering a mistake later
    fr = "fr"
    fo = "fo"
    nfr = "nfr"
    nfo = "nfo"
    
    d={'cypher1':[],'cypher2':[],'group_ids':[]} #this is used to make a modifiable closure variable
        
    #build and run the query
    def make_group_match_cypher(groups,group_id_prefix):
        for i,group in enumerate(groups):
            group_id = group_id_prefix+str(i)+"_id"
            user_list = _escape_user_list(group)
            group_ids_str = ", ".join(d['group_ids']) + ", " if len(d['group_ids']) > 0 else ""
            d['cypher1'].append(("MATCH (x:User) WHERE x.screen_name IN {user_list}\n"
                           "  WITH {group_ids_str}collect(id(x)) AS {group_id}"
                           ).format(user_list=user_list,group_ids_str =group_ids_str,group_id=group_id))
            d['group_ids'].append(group_id)
            d['cypher2'].append("id({0}) IN {1}".format(group_id_prefix+str(i),group_id))
                
    make_group_match_cypher(friendingUsers,fr)
    make_group_match_cypher(followedUsers,fo)
    
    query = "\n\n".join(d['cypher1'])
    query += "\n\nMATCH\n"
    cypher_clauses = []
    for i,group in enumerate(friendingUsers):
        group_id = fr+str(i)
        cypher_clauses.append("  ({group_id})-[:FOLLOWS]->(target)".format(group_id=group_id))
    for i,group in enumerate(followedUsers):
        group_id = fo+str(i)
        cypher_clauses.append("  (target)-[:FOLLOWS]->({group_id})".format(group_id=group_id))
    query += ",\n".join(cypher_clauses)
    query += "\nWHERE\n      "
    query += "\n  AND ".join(d['cypher2'])
    query += ("\nRETURN count(*) AS count, target\n"
                "ORDER BY count DESC\n"
                "LIMIT 1000;"
            )
    
    return query






