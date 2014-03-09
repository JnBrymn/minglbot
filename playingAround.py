import time
import sys
 
import tweepy
from tweepy import Cursor


import pdb;pdb.set_trace()
#get tweepy set up
TWITTER_CONSUMER_KEY="0xr5gEg5zWHaFETJBjtXhA"
TWITTER_CONSUMER_SECRET="fTvUmnkNbhIQjbRLElR7n745WBw0e7bkUq4PKKUv4Q"
TWITTER_BOT_TOKEN="28881634-YRjPqP1f8MlwcsxsEAoufdeNtdXCQOg5VPLXnFD1k"
TWITTER_BOT_SECRET="7MJ3jtLETB5S53C387oFaBaGohrbyrPG9JfPX0OTsXoDE"
auth = tweepy.OAuthHandler(TWITTER_CONSUMER_KEY, TWITTER_CONSUMER_SECRET)
auth.set_access_token(TWITTER_BOT_TOKEN, TWITTER_BOT_SECRET)
api = tweepy.API(auth)
#user = api.get_user('twitter')
user = api.lookup_users(['twitter'])

print "done"

