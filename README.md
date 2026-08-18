Ruuvi Dash is a small flask web application designed to accept and store weather data from the Ruuvi Gateway and display it on a dashboard.

- Accepts JSON data from Ruuvi Gateway (currently only accepts decoded data)
- Dashboard updates in real time with web sockets
- Graphing of data from sqlite database

##

### To run:

First install required modules:

```
uv sync
```

Then run with gunicorn:

```
gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --bind localhost:8000 app.app:app
```
alternatively, to run with docker:
```
docker build -t ruuvidash .
docker run -d -p 8000:8000 ruuvidash
```

Then in your Ruuvi Gateway settings, choose custom and set the URL of where you're hosting ruuvi-dash.
For example:
www.ruuvidash.xyz/request
