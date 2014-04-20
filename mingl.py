#TODOs
#all friend getters multidirectional (e.g. friend or follow)
## _get_friends_from_twitter
## get_mutual_friends
#make "in between" function to find popular users U s.t. A-->U<--B
#make the hydration preserve the ordering and grouping
#make log messages be code that you can copy and paste and run
#figure out why the uniqueness constraints aren't being set by default
#handle users that don't allow their friends to be seen by marking them as friends_found_at - similarly for hydrated
#?figure out why I'm haveing to double get friends to get them all (try running a get central nodes run and then do it again... it pulls in new friends... should be the same)
#"figure out why I'm haveing to double hydrate long lists users that come back from get_mutual_friends. The first hydrate doesn't get them all.
#encapsulate the graphQueries and log them to a different file
#turn off neo4jlogging
#create warning if friends are too popular?
#make an "introductions" query? really, you'd often want an introduction to the FOLLOWERS of some group if you're recruiting
##introduction should also take into account if they're already following you. You also need to know why someone should follow you
#make twitter and graph private and make all *_at attributes @properties
#handle nonexistant (friends and hydration)
#figure out what to do with other API tokens - this can be used to greatly increase my throughput
#guard against "could not authenticate" code 32
#guard against "deadlock" if using more than one process that talks to neo4
#add a real testing environment

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
    def twitter_exception_handling_runner(cls,func,**args):
        retrySeconds = 60*5
        while True:
            try:
                return func(**args)
            except tweepy.TweepError as e:
                if e.reason == "Not authorized.":
                    logging.info("Not authorized.") #TODO return errors when necessary
                    return [] #TODO is empty array the correct thing to return?
                elif e[0][0]["code"] == 88:
                    logging.info("Rate limit exceeded. Sleeping")
                    time.sleep(retrySeconds)
                else:
                    logging.error("Unexpected error: %s",e)
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
            twitter_users = Mingl.twitter_exception_handling_runner(self.twitter.lookup_users, user_ids=ids, screen_names=screen_names)
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

    def hydrate_users(self,users,num_to_use=float("inf")):
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
            WHERE u.id in {ids} 
             OR u.screen_name in {screen_names}
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

    def _get_friends_from_twitter(self,user,return_users=True):
        logging.info("Getting friends of %s from Twitter",user)
        ids = []
        query = ""
        if isinstance(user,int):
            ids = Mingl.twitter_exception_handling_runner(self.twitter.friends_ids,user_id=user,count=5000)
            query += "MERGE (a:User {id:{id}})"
        elif isinstance(user,basestring):
            user = user.lower()
            ids = Mingl.twitter_exception_handling_runner(self.twitter.friends_ids,screen_name=user,count=5000)
            query += "MERGE (a:User {screen_name:{screen_name}})"
        else:
            err_msg = "user must be either integer for id, string for screen_name. Found %s" % str(user)
            logging.error(err_msg)
            raise Exception(err_msg)
        query += """
            ON CREATE SET
              a.created_at = timestamp()
            SET a.friends_found_at = timestamp()
            FOREACH (id IN {ids} |
              MERGE (b:User {id:id})
              ON CREATE SET
                b.created_at = timestamp()
              CREATE UNIQUE (a)-[:FOLLOWS]->(b)
            )
        """
        neo4j.CypherQuery(self.graph,query).run(id=user,screen_name=user,ids=ids)

        if return_users:
            users = []
            for id in ids:
                user = User(id)
                user.created_at = 1
                users.append(user)
            return users

    def get_mutual_friends(self,
            users,
            num_to_use=float("inf"),
            limit=100,
            min_num_mutual_friends=1
            ):
        """Retrieve mutual friends.

        Keyword arguments:
        num_to_use -- issues query based only upon the first num_to_use users (default inf)
        limit -- the number of friends to return (default 100)
        min_num_mutual_friends -- all users returned must be mutual friends of this number of input friends (defaul 1)
        """
        input = Mingl._split_up_input(users,{int:"ids",basestring:"screen_names",User:"users"},num_to_use=num_to_use)
        ids = input["ids"]
        screen_names = input["screen_names"]
        for the_user in input["users"]:
            #TODO make this method more efficient by not adding ids for users with friends_found_at
            if the_user.id:
                ids.append(the_user.id)
            else:
                screen_names.append(the_user.screen_name)
        logging.info("Getting mutual friends. ids:(%s) screen_names:(%s)",ids,screen_names)

        #First, get list of users for whom friends have not been retrieved
        if screen_names:
            screen_names = [screen_name.lower() for screen_name in screen_names]
        all_ids = copy.copy(ids)
        all_screen_names = copy.copy(screen_names)
        getUsersQuery = """
            MATCH (u:User)
            WHERE u.id in {ids} 
             OR u.screen_name in {screen_names}
            RETURN u
        """
        for u in neo4j.CypherQuery(self.graph,getUsersQuery).execute(ids=ids,screen_names=screen_names):
            user = u.values[0]
            if user["friends_found_at"]:
                if user["id"] and (user["id"] in ids):
                    ids.remove(user["id"])
                if user["screen_name"]:
                    screen_name = user["screen_name"].lower()
                    if screen_name in screen_names: screen_names.remove(screen_name)

        #Load these users into neo4j
        ids.extend(screen_names)
        for id in ids:
            self._get_friends_from_twitter(id,return_users=False)

        #Retrieve list of mutual friends sorted by number of mutual friendships
        query = """
            MATCH (u:User)-[:FOLLOWS]->(f:User)
            WHERE u.screen_name in {screen_names}
               OR u.id in {ids}
            WITH count(*) AS c,f
            ORDER BY c desc
            LIMIT {limit}
            WHERE c >= {min_num_mutual_friends}
            RETURN c, f
        """
        results = neo4j.CypherQuery(self.graph,query).execute(
            ids=all_ids,
            screen_names=all_screen_names,
            limit=limit,
            min_num_mutual_friends=min_num_mutual_friends
        )
        friends = defaultdict(list)
        for r in results:
            friends[r.values[0]].append(User(r.values[1].get_properties()))
        return GroupedUsers(friends)

