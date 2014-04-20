#TODO
# Add stalker capability to pull in more people - see tiddlywiki for details
# implement jobs left 

import os
import logging #see http://docs.python.org/2/howto/logging
import tweepy
from Queue import PriorityQueue
import mingl
import datetime
import time

m = mingl.Mingl(os.getenv("TWITTER_CONSUMER_KEY"), os.getenv("TWITTER_CONSUMER_SECRET"))
class Job(object):
    def __init__(self,id,screen_names,author):
        self.id = id
        self.screen_names = screen_names
        self.author = author
        
    def __repr__(self):
        return "{0}:{1}:{2}".format(self.id,','.join(self.screen_names),self.author)

class JobQueue(object):
    def __init__(self):
        self._priorityQueue = PriorityQueue()
    
    def put(self,job,priority_metric):
        self._priorityQueue.put_nowait((-priority_metric,job))
        
    def get(self):
        try:
            return self._priorityQueue.get_nowait()[1]
        except Exception:
            return None
    
    def __iter__(self):
        job = True
        while job:
            job = self.get()
            yield job
        
class TwitterBot(object):
    def __init__(self,
                 twitter_consumer_key,
                 twitter_consumer_secret,
                 bot_screen_name = "minglbot",
                 response_history_file="response_history.txt",
                 twitter_bot_token=None,
                 twitter_bot_secret=None,
                 refresh_jobs_period=5*60, #seconds - how often to read the bot's twitter mentions and refresh the job queue
                 min_screen_names = 6
                ):
        logging.basicConfig(filename="twitterbot.log",level=logging.INFO)
        logging.info("Initializing TwitterBot")
        twitter_bot_token = twitter_bot_token if twitter_bot_token else os.getenv("TWITTER_BOT_TOKEN")
        twitter_bot_secret = twitter_bot_secret if twitter_bot_secret else os.getenv("TWITTER_BOT_SECRET")
        auth = tweepy.OAuthHandler(twitter_consumer_key, twitter_consumer_secret)
        auth.set_access_token(twitter_bot_token, twitter_bot_secret)
        self._twitter = tweepy.API(auth)
        self._screen_name = bot_screen_name.lower()
        self._response_history_file = response_history_file
        self._refresh_jobs_period = refresh_jobs_period
        self._mingl = mingl.Mingl(os.getenv("TWITTER_CONSUMER_KEY"), os.getenv("TWITTER_CONSUMER_SECRET"))
        self._job_queue = JobQueue()
        self._since_id = 1 #message status id to start with. by default start reading from the beginning of time
        self._min_screen_names = min_screen_names
        
        #collect all completed job ids
        try:
            with open(response_history_file) as f:
                self._done_job_ids = set([int(line.strip()) for line in f])
        except IOError, e:
            logging.fatal("trouble opening response_history.txt: {0}".format(e))
            exit(1)
        
    def _refresh_jobs(self):
        num_jobs = 0
        mentions = self._twitter.mentions_timeline(since_id=self._since_id,count=800)
        for mention in mentions:
            if mention.id in self._done_job_ids:
                continue
            screen_names = []
            for user in mention.entities["user_mentions"]:
                screen_name = user["screen_name"].lower()
                if screen_name != self._screen_name:
                    screen_names.append(screen_name)
            if len(screen_names) > self._min_screen_names:
                num_jobs += 1
                self._job_queue.put(
                    Job(mention.id, screen_names, mention.author.screen_name.lower()),
                    mention.author.followers_count
                )
        logging.info("Refreshed job queue. Found {0} jobs".format(num_jobs))
        self._since_id = mention.id 
        
    def _execute_job(self):
        job = self._job_queue.get()
        if not job:
            logging.info(u"No more jobs to do. Sleeping.")
            time.sleep(60)
            return False
        logging.info(u"Executing job: {0}".format(job))
        
        #####################
        # find best friends #
        #####################
        #get mutual friends, hydrate, and then retrieve them again from Neo4J
        #the reason for the double retrieval is that the hydration throws away the ordering and grouping
        friends = self._mingl.get_mutual_friends(job.screen_names)
        m.hydrate_users(friends)
        friends = self._mingl.get_mutual_friends(job.screen_names)
        
        #get only the friends that about half of them know
        popularity = len(job.screen_names)/2
        if popularity < 3:
            popularity = 3
        friends = friends.get_all_with_min_popularity(popularity)
        if len(friends) > 3:
            tweet = "@{0}, their best friends:".format(job.author)
            for friend in friends:
                if len(tweet)<=140:
                    tweet += " @"+friend.screen_name
        else:
            tweet = "@{0}, these users don't seem to have much in common".format(job.author)
        logging.info("Sending tweet: "+tweet)
        self._send_tweet(tweet,job.id)
    
        ######################
        # find central nodes #
        ######################
        
        ######################
        # find central topic #
        ######################
        
        ##############################
        # find venues for connection #
        ##############################
        
        with open(self._response_history_file,'a') as f:
            f.write("{0}\n".format(job.id))
        self._done_job_ids.add(job.id)
        return True

    def _send_tweet(self,tweet,job_id):
        """thin wrapper so that I won't send tweets to my account"""
        if self._screen_name == "jnbrymn":
            return
        self._twitter.update_status(tweet,job_id)
    
    def run(self):
        last_job_refresh = datetime.datetime.min
        while(True):
            if (datetime.datetime.now()-last_job_refresh).seconds > self._refresh_jobs_period:
                self._refresh_jobs()
                last_job_refresh=datetime.datetime.now()
            self._execute_job()


if __name__ == "__main__":
    t=TwitterBot(os.getenv("TWITTER_CONSUMER_KEY"), os.getenv("TWITTER_CONSUMER_SECRET"),os.getenv("TWITTER_SCREEN_NAME"),min_screen_names=1)
    t.run()