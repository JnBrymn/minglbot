from flask import Flask
import json

app = Flask(__name__)

@app.route("/")
def hello():
    return json.dumps([ { 'a':'A', 'b':(2, 4), 'c':3.0 } ])

if __name__ == "__main__":
    app.run()