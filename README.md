minglbot
========

getting started
---------------
* start neo4j
* run minglbo_test.py (and read it)
* open up ipython notebook

other information
-----------------
* mingl.py - Basically a set of commands that allows you to query social groups in twitter. It uses Neo4j as a read-through cache.
* mingl.log - the log
* response_history.txt tracks the messages that
* bot.py - listens to a twitter account and makes tweets
* see issues on github
* tests: get_user_test.py mingl_test.py 


typical usage
-------------
```python
#Instantiate mingl engine
import mingl
reload(mingl)
import os
m = mingl.Mingl(os.getenv("TWITTER_CONSUMER_KEY"), os.getenv("TWITTER_CONSUMER_SECRET"))

#get friends of a group of twitter users
osc=["dep4b","hull_j","scottstults","omnifroodle","jnbrymn","softwaredoug","danielbeach","patriciagorla","jwoodell"]
friends = m.get_friends(osc)

#hydrate them
friends = m.hydrate_users(friends)

#because hydration currently doesn't preserve ordering or grouping you have to get_friends again (see https://github.com/JnBrymn/minglbot/issues/5)
friends = m.get_friends(osc)

#print them	
for k,v in friends.iteritems():
    print k
    for u in v:
        #print "\t", u.screen_name, u.id#,"\n\t\t",u["name"],"\n\t\t",u["description"],"\n\n"
        print "\t", u.screen_name
```

copyright
---------
OH... and everything in this repo is copyright John Berryman 2014. This code shall not be reproduce for any purpose without my written consent in 3 different languages (and it'll take me a while to look up all the words in Japanese). Also, the functionality of this code shall not be publically disclosed, for example in the form of a twitter bot or a publically available API, without my written consent in 3 different languages.