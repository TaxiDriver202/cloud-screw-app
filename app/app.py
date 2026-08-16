# SPDX-FileCopyrightText: 2025 Topias Silfverhuth
# SPDX-License-Identifier: MIT

import logging
import sqlite3
from os import getenv

import pandas as pd
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

log = logging.getLogger("ruuvi-dash")
logging.basicConfig(level=logging.DEBUG)

dbconn = sqlite3.connect("ruuvidata.db")
cur = dbconn.cursor()
cur.execute(
    "CREATE TABLE IF NOT EXISTS data(id int, temperature float, humidity float, pressure float, date timestamptz)"
)
dbconn.commit()

UPDATE_INTERVAL: int = 10
ADMIN_PASSWORD: str = getenv("RUUVIDASH_PASSWORD", "javasdk8")

updata_counter: int = 0

tag_names = []
RTags = {}

# Metric slug -> (heading, unit) used by the graph page.
METRICS = {
    "temperature": ("Temperature", "°C"),
    "humidity": ("Humidity", "%"),
    "pressure": ("Pressure", "kPa"),
}

# (value, interval, button label) for the graph page range selector.
PRESETS = [
    (1, "hours", "1 hour"),
    (1, "days", "1 day"),
    (1, "weeks", "1 week"),
    (4, "weeks", "1 month"),
]

# Upper bound on points drawn per sensor; longer ranges get thinned out.
MAX_POINTS = 600


def tag_label(index: int) -> str:
    """Display name for a sensor, falling back to its index."""
    if len(tag_names) > index and tag_names[index]:
        return tag_names[index]
    return f"Tag {index}"


def update_database():
    try:
        for i, tag in enumerate(RTags.values()):
            log.debug(f" i: {i}, tag: {tag}")
            cur.execute(
                f"INSERT INTO data(id, temperature, humidity, pressure, date) VALUES ('{i}', {tag.get('temperature')}, {tag.get('humidity')}, {tag.get('pressure', 0)}, datetime('now', 'localtime'));"
            )
        cur.execute(
            "DELETE FROM data WHERE date < datetime('now', 'localtime', '-1 years');"
        )
        dbconn.commit()
        log.info(" Inserted data into db")
    except Exception as e:
        log.error(" Data collection failed: %s" % e)


def update_data(data):
    global RTags
    global updata_counter

    if len(data) != len(RTags):
        RTags = {}

    for tag in data:
        RTags[tag] = {
            "temperature": data[tag].get("temperature", 0),
            "humidity": data[tag].get("humidity", 0),
            "pressure": (data[tag].get("pressure", 0) / 1000),
        }
    packets = {tag: val for (tag, val) in enumerate(RTags.values())}

    updata_counter += 1
    if updata_counter > UPDATE_INTERVAL:
        update_database()
        updata_counter = 0
    socketio.emit("data_update", packets)
    return packets


"""ROUTES"""


@app.route("/graph/<item>")
def graph(item):
    try:
        if item not in METRICS:
            item = "temperature"
        metric_label, unit = METRICS[item]

        timevalue = request.args.get("value", 1, type=int)
        timevalue = max(1, min(timevalue or 1, 520))
        interval = request.args.get("interval", "hours", type=str)
        if interval not in ("hours", "days", "weeks"):
            interval = "hours"
        log.debug(f"item: {item}, timevalue: {timevalue}, interval: {interval}")

        time = timevalue
        if interval == "weeks":
            time = time * 24 * 7
        elif interval == "days":
            time = time * 24

        df = pd.read_sql(
            f"SELECT * FROM data where date > datetime('now', 'localtime', '-{time} hours');",
            dbconn,
            index_col=None,
        ).groupby("id")

        # Initialize lists to store all data
        all_values = []
        all_tags = []

        for id, group in df:
            # ISO timestamps so the chart can lay points out on a real time axis.
            dates = (
                pd.to_datetime(group.date, errors="coerce")
                .dt.strftime("%Y-%m-%dT%H:%M:%S")
                .tolist()
            )
            values = list(zip(dates, group[item].tolist()))

            # Thin dense ranges: drawing a month of samples is unreadable and slow.
            if len(values) > MAX_POINTS:
                step = len(values) // MAX_POINTS + 1
                thinned = values[::step]
                if thinned[-1] != values[-1]:
                    thinned.append(values[-1])
                values = thinned

            all_values.append(values)
            all_tags.append(tag_label(int(id)))

        presets = [
            {
                "value": v,
                "interval": i,
                "label": label,
                "active": v == timevalue and i == interval,
            }
            for v, i, label in PRESETS
        ]
        range_label = (
            f"last {interval[:-1]}"
            if timevalue == 1
            else f"last {timevalue} {interval}"
        )

        # Tick granularity: clock times only make sense over a couple of days.
        if time <= 3:
            time_unit = "minute"
        elif time <= 48:
            time_unit = "hour"
        else:
            time_unit = "day"

        return render_template(
            "graph.html",
            all_values=all_values,
            all_tags=all_tags,
            active=item,
            metric_label=metric_label,
            unit=unit,
            value=timevalue,
            interval=interval,
            presets=presets,
            range_label=range_label,
            time_unit=time_unit,
            point_count=sum(len(v) for v in all_values),
        )
    except Exception as e:
        log.error(e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/graph")
@app.route("/graph/")
def graph_redirect():
    return graph("temperature")


@app.route("/supersecretadmin")
def admin():
    global tag_names

    names = []
    for i in range(len(RTags)):
        names.append(request.args.get(f"tag{i}", "", type=str))
        # log.debug(request.args.get(f"tag{i}", "", type=str))

    for i, name in enumerate(names):
        if name != "":
            if len(tag_names) > i:
                tag_names[i] = name
            else:
                log.debug(f"appending {name}")
                tag_names.append(name)

    passwd: str | None = request.args.get("pass", type=str)
    weeks: int | None = request.args.get("weeks", type=int)
    if passwd == ADMIN_PASSWORD and weeks is not None and weeks >= 0:
        try:
            cur.execute(
                f"DELETE FROM data WHERE date < datetime('now', 'localtime', '-{weeks * 7} days');"
            )
            dbconn.commit()
            log.info(f"successfully deleted data older than {weeks} weeks")
        except Exception as e:
            log.error(e)
            return jsonify({"status": "error", "message": str(e)}), 500
    return render_template("admin.html", active="admin", tag_names=tag_names)


@app.route("/")
@app.route("/dashboard")
def dashboard():
    data = {i: tag for (i, tag) in enumerate(RTags.values())}
    return render_template(
        "dashboard.html", data=data, tag_names=tag_names, active="dashboard"
    )


@app.route("/request", methods=["POST"])
def request_data():
    """
    Receives gateway data in json and sends processed data to clients through websocket
    """
    try:
        log.info(request.get_json())
        tags = request.get_json()["data"]["tags"]
        packets = update_data(tags)

        return jsonify({"status": "success", "data": packets}), 200
    except Exception as e:
        log.error(e)
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)

# command for gunicorn(for docker place in dockerfile CMD[]):
# gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 --bind 0.0.0.0:5000 app.app:app
