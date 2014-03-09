#TODOs
#make twitter and graph private and make all *_at attributes @properties
#handle nonexistant (friends and hydration)
#handle secret users (friends and hydration)
#change _get_user_from_neo4j to userS (plural)
#guard against "could not authenticate" code 32

import os
import logging #see http://docs.python.org/2/howto/logging
logging.basicConfig(filename="minglbot.log",level=logging.INFO)

class User(object):
    def __init__(self,user):
        self.id = None
        self.screen_name = None
        self.created_at = None
        self.hydrated_at = None
        self.friends_found_at = None
        self._properties = {}
        if type(user) is int:
            self.id = user
        elif type(user) is str:
            self.screen_name = user.lower()
        elif type(user) is dict:
            identified = False
            if "id" in user:
                self.id = user["id"]
                identified = True
            if "screen_name" in user:
                self.screen_name = user["screen_name"].lower()
                identified = True
            if not identified:
                raise Exception("all users must have either an id or a screen_name")
            if "created_at" in user:
                self.created_at = user["created_at"]
            if "hydrated_at" in user:
                self.hydrated_at = user["hydrated_at"]
            if "friends_found_at" in user:
                self.friends_found_at = user["friends_found_at"]
            self._properties = user
        elif isinstance(User(id=100),User):
            raise NotImplementedError()
        
    @property
    def identifier(self):
        if self.id:
            return id
        else:
            return screen_name
    
    def __getitem__(self,key):
        return self._properties[key]

    def __repr__(self):
        return "User(id=%s,screen_name=%s)" % (str(self.id), self.screen_name)


#Utilities
retrySeconds = 60*5
def timedRetry(func,**args):
    while True:
        try:
            return func(**args)
        except tweepy.TweepError as e:
            if e[0][0]["code"] == 88:
                logging.info("Rate limit exceeded. Sleeping")
                time.sleep(retrySeconds)
            else:
                logging.error("Unexpected error: %s",e)
                raise e

from collections import defaultdict
import time
import tweepy
from py2neo import neo4j
import copy

class MinglBot(object):
    @classmethod
    def split_up_input(cls,input,types_map,error_on_unknown_type=True):
        if not isinstance(input,list):
            input = [input]
        d = defaultdict(list)
        for i in input:
            for t,n in types_map.iteritems():
                if isinstance(i,t):
                    d[n].append(i)
                    break
            else:
                if error_on_unknown_type:
                    raise Exception("unsupported %s" % type(i))
                    logger.error("unsupported %s" % type(i))
        #d.default_factory = lambda:None #I was using this, but found that it caused unnecessary problems
        #keeping it here for now because it's an idiom that I always forget
        return d
             
    def __init__(self,
                 twitter_consumer_key,
                 twitter_consumer_secret,
                 twitter_bot_token=None,
                 twitter_bot_secret=None,
                 neo4j_host=None):
        logging.info("Initializing MinglBot")
        twitter_bot_token = twitter_bot_token if twitter_bot_token else os.getenv("TWITTER_BOT_TOKEN")
        twitter_bot_secret = twitter_bot_secret if twitter_bot_secret else os.getenv("TWITTER_BOT_SECRET")
        auth = tweepy.OAuthHandler(twitter_consumer_key, twitter_consumer_secret)
        auth.set_access_token(twitter_bot_token, twitter_bot_secret)
        self.twitter = tweepy.API(auth)
        
        neo4j_host = neo4j_host if neo4j_host else os.getenv("NEO4J_HOST")
        from py2neo import neo4j
        self.graph = neo4j.GraphDatabaseService("http://"+ neo4j_host +"/db/data")
        
        #TODO move this to init script
        try:
            logging.info("Creating uniqueness constraint on User id and screen_name")
            
            neo4j.CypherQuery(graph,"""
                CREATE CONSTRAINT ON (u:User) 
                ASSERT u.id IS UNIQUE
            """).execute()
            neo4j.CypherQuery(graph,"""
                CREATE CONSTRAINT ON (u:User) 
                ASSERT u.screen_name IS UNIQUE
            """).execute()
        except:
            pass
    
    def _get_user_from_neo4j(self,user):
        logging.info("Getting user (%s) from neo4j",user)
        if type(user) is int:
            query = "MATCH (u:User{id:{id}}) RETURN u"
            u = neo4j.CypherQuery(self.graph,query).execute_one(id=user)
            user = User(user)
            if u is None:
                return None
            if u["screen_name"]:
                user.screen_name = u["screen_name"].lower()
        elif type(user) is str:
            query = "MATCH (u:User{screen_name:LOWER({screen_name})}) RETURN u"
            u = neo4j.CypherQuery(self.graph,query).execute_one(screen_name=user.lower())
            user = User(user)
            if u is None:
                return None
            if u["id"]:
                user.id = u["id"]
        else:
            logging.error("User was neither id or screen_name")
            raise Exception("user must be either integer for id, string for screen_name")
        user._properties = dict(user._properties.items() + u.get_properties().items())
        if u["created_at"]:
            user.created_at = u["created_at"]
        if u["hydrated_at"]:
            user.hydrated_at = u["hydrated_at"]
        if u["friends_found_at"]:
            user.friends_found_at = u["friends_found_at"] 
        return user
    
    #Creates user in neo4j based upon string for screen_name or int for id
    def _create_user_in_neo4j(self,user):
        logging.info("Creating user (%s) in neo4j",user)
        if type(user) is int:
            query = """
                MERGE (u:User {id:{id}})
                ON CREATE SET
                    u.created_at = timestamp()
                RETURN u
            """
            u = neo4j.CypherQuery(self.graph,query).execute_one(id=user)    
        elif type(user) is str:
            query = """
                MERGE (u:User {screen_name:LOWER({screen_name})})
                ON CREATE SET
                    u.created_at = timestamp()
                RETURN u
            """
            u = neo4j.CypherQuery(self.graph,query).execute_one(screen_name=user.lower())
        else:
            logging.error("User was neither id nor screen_name")
            raise Exception("user must be either integer for id, string for screen_name")
        return User(u.get_properties())

            
    def _delete_user_from_neo4j(self,user):
        logging.info("Deleting user (%s) from neo4j",user)
        if type(user) is int:
            query = """
                MATCH (u:User {id:{id}})
                OPTIONAL MATCH (u)-[r]-()
                DELETE u,r
            """
            u = neo4j.CypherQuery(self.graph,query).run(id=user)    
        elif type(user) is str:
            query = """
                MATCH (u:User {screen_name:LOWER({screen_name})})
                OPTIONAL MATCH (u)-[r]-()
                DELETE u,r
            """
            u = neo4j.CypherQuery(self.graph,query).run(screen_name=user.lower())
        else:
            logging.error("User was neither id nor screen_name")
            raise Exception("user must be either integer for id, string for screen_name")
    
    #Pulls up to 100 users from twitter by id or by screen_name.
    #If there is an id/screen_name conflict caused by two nodes representing the
    #same user, then this method will combine the two nodes including their FOLLOWs
    #relationships. Currently metadata can be lost such as the original created_at date
    def _hydrate_users_from_twitter(self,users):
        input = MinglBot.split_up_input(users,{int:"ids",str:"screen_names"})
        ids = input["ids"]
        screen_names = input["screen_names"]
        logging.info("Hydrating ids (%s) and screen_names (%s) from Twitter",ids,screen_names)
        if screen_names:
            screen_names = [screen_name.lower() for screen_name in screen_names]
        twitter_users = []
        if (ids and len(ids)>0) or (screen_names and len(screen_names)>0) :
            twitter_users = timedRetry(self.twitter.lookup_users, user_ids=ids, screen_names=screen_names)
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
    
    #Attempts to hydrate users from neo4j. If user is not present or if hydrated_at
    #is None then this method will hydrate the users from Twitter
    def hydrate_users(self,users):
        input = MinglBot.split_up_input(users,{int:"ids",str:"screen_names",User:"users"})
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

    def get_friends_for_user(self,user):
        logging.info("Getting friends of user (%s) (from neo4j if possible)",user)
        users = []
        this_user = None
        query = """
            MATCH (u:User {id:{id}})-[:FOLLOWS]->(f)
            RETURN f
        """
        if type(user) is int:
            this_user = self._get_user_from_neo4j(user)
            identifier = user
        elif type(user) is str:
            user = user.lower()
            identifier = user            
            query = """
                MATCH (u:User {screen_name:LOWER({screen_name})})-[:FOLLOWS]->(f)
                RETURN f
            """
            this_user = self._get_user_from_neo4j(user)
        elif type(user) == User:
            this_user = user
            identifier = this_user.id
        else:
            raise Exception("user must be either integer for id, string for screen_name, or User")
        if this_user == None:
            this_user = self._create_user_in_neo4j(identifier)
        if this_user.hydrated_at:
            us = neo4j.CypherQuery(self.graph,query).execute(id=identifier,screen_name=identifier)
            for u in us:
                users.append(User(u.values[0].get_properties()))
            return users
        else:
            return self._get_friends_from_twitter(identifier)
            

    def _get_friends_from_twitter(self,user,return_users=True):
        logging.info("Getting friends of %s from Twitter",user)
        ids = []
        query = ""
        if type(user) is int:
            ids = timedRetry(self.twitter.friends_ids,user_id=user,count=5000)
            query += "MERGE (a:User {id:{id}})"
        elif type(user) is str:
            user = user.lower()
            ids = timedRetry(self.twitter.friends_ids,screen_name=user,count=5000)
            query += "MERGE (a:User {screen_name:{screen_name}})"
        else:
            raise Exception("user must be either integer for id, string for screen_name")
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
    
    def get_mutual_friends(self,users,limit=100,min_num_mutual_friends=2):
        input = MinglBot.split_up_input(users,{int:"ids",str:"screen_names",User:"users"})
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
                id = user["id"]
                if user["screen_name"]:
                    screen_name = user["screen_name"].lower()
                if id in ids: ids.remove(id)
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
        return friends

